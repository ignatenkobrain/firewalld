#
# Copyright (C) 2011-2012 Red Hat, Inc.
# Authors:
# Thomas Woerner <twoerner@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import time
from firewall.core.base import *
from firewall.core.logger import log
from firewall.functions import portStr
from firewall.errors import *

class FirewallZone:
    def __init__(self, fw):
        self._fw = fw
        self.__init_vars()

    def __init_vars(self):
        self._chains = { }
        self._zones = { }

    def cleanup(self):
        self.__init_vars()

    # zones

    def get_zones(self):
        return self._zones.keys()

    def get_zone_of_interface(self, interface):
        self.check_interface(interface)
        for zone in self._zones:
            if interface in self._zones[zone].interfaces:
                # an interface can only be part of one zone
                return zone
        return None

    def get_zone(self, zone):
        z = self._fw.check_zone(zone)
        return self._zones[z]

    def add_zone(self, obj):
        obj.interfaces = [ ]
        obj.settings = { }
        for x in [ "interfaces", "services", "ports", "masquerade",
                   "forward_ports", "icmp_blocks" ]:
            obj.settings[x] = { }

        self._zones[obj.name] = obj

        # apply default zone settings from config files
        for args in obj.interfaces:
            self.check_interface(args)
            self.__interface(True, obj.name, args)
        for args in obj.icmp_blocks:
            self.check_icmp_block(*args)
            self.__icmp_block(True, obj.name, *args)
        for args in obj.forward_ports:
            self.check_forward_port(*args)
            mark = self._fw.new_mark()
            self.__forward_port(True, obj.name, *args, mark_id=mark)
        for args in obj.services:
            self.check_service(args)
            self.__service(True, obj.name, args)
        for args in obj.ports:
            self.check_port(*args)
            self.__port(True, obj.name, *args)
        if obj.masquerade:
            self.__masquerade(True, obj.name)

    def remove_zone(self, zone):
        obj = self._zones[zone]
        obj.interfaces = [ ]
        obj.settings.clear()
        del self._zones[zone]

    def is_immutable(self, zone):
        return self._zones[zone].immutable

    def check_immutable(self, zone):
        if self.is_immutable(zone):
            raise FirewallError(IMMUTABLE)

    # dynamic chain handling

    def __chain(self, zone, create, table, chain):
        if zone in self._chains and table in self._chains[zone] and \
                chain in self._chains[zone][table]:
            return

        # do not create chains for immuable zones
        if self.is_immutable(zone):
            return

        chains = [ ]
        rules = [ ]
        zones = [ self._zones[zone].target.format(chain=SHORTCUTS[chain],
                                                  zone=zone) ]

        # TODO: simplify for one zone only
        for _zone in zones:

            ipvs = [ "ipv4" ]
            if table != "nat":
                # no nat for ipv6
                ipvs.append("ipv6")

            for ipv in ipvs:
                chains.append((ipv, [ _zone, "-t", table ]))
                chains.append((ipv, [ "%s_deny" % (_zone), "-t", table ]))
                chains.append((ipv, [ "%s_allow" % (_zone), "-t", table ]))
                rules.append((ipv, [ _zone, 1, "-t", table,
                                     "-j", "%s_deny" % (_zone) ]))
                rules.append((ipv, [ _zone, 2, "-t", table,
                                     "-j", "%s_allow" % (_zone) ]))
                if table == "filter":
                    rules.append((ipv, [ _zone, 3, "-t", table,
                                         "-j", "%%REJECT%%" ]))

        if create:
            # handle chains first
            ret = self._fw.handle_chains(chains, create)
            if ret:
                (cleanup_chains, msg) = ret
                log.debug2(msg)
                self._fw.handle_chains(cleanup_chains, not create)
                # TODO: log msg
                if create:
                    raise FirewallError(ADD_FAILED)
                else:
                    raise FirewallError(REMOVE_FAILED)

            # handle rules
            ret = self._fw.handle_rules(rules, create, insert=True)
            if ret:
                # also cleanup chains
                self._fw.handle_chains(chains, not create)

                (cleanup_rules, msg) = ret
                self._fw.handle_rules(cleanup_rules, not create)
                # TODO: log msg
                if create:
                    raise FirewallError(ADD_FAILED)
                else:
                    raise FirewallError(REMOVE_FAILED)
        else:
            # cleanup rules first
            ret = self._fw.handle_rules(rules, create, insert=True)
            if ret:
                (cleanup_rules, msg) = ret
                self._fw.handle_rules(cleanup_rules, not create)
                # TODO: log msg
                if create:
                    raise FirewallError(ADD_FAILED)
                else:
                    raise FirewallError(REMOVE_FAILED)
            
            # cleanup chains
            ret = self._fw.handle_chains(chains, create)
            if ret:
                # also create rules
                self._fw.handle_rules(cleanup_rules, not create)

                (cleanup_chains, msg) = ret
                self._fw.handle_chains(cleanup_chains, not create)
                # TODO: log msg
                if create:
                    raise FirewallError(ADD_FAILED)
                else:
                    raise FirewallError(REMOVE_FAILED)

        if create:
            self._chains.setdefault(zone, { }).setdefault(table, [ ]).append(chain)
        else:
            self._chains[zone][table].remove(chain)
            if len(self._chains[zone][table]) == 0:
                del self._chains[zone][table]
            if len(self._chains[zone]) == 0:
                del self._chains[zone]

    def add_chain(self, zone, table, chain):
        self.__chain(zone, True, table, chain)

    def remove_chain(zone, self, table, chain):
        # TODO: add config setting to remove chains optionally if 
        #       table,chain is not used for zone anymore
#        self.__chain(zone, False, table, chain)
        pass

    # settings

    # generate settings record with sender, timeout, mark
    def __gen_settings(self, timeout, sender, mark=None):
        ret = {
            "date": time.time(),
            "sender": sender,
            "timeout": timeout,
        }
        if mark:
            ret["mark"] = mark
        return ret

    def get_settings(self, zone):
        return self.get_zone(zone).settings

    def set_settings(self, zone, settings):
        _obj = self.get_zone(zone)
        _obj.settings = settings

        try:
            for key in settings:
                # do not re add timeout features
                keys = settings[key].keys()
                for args in keys:
                    if "timeout" in settings[key][args]:
                        del _obj.settings[key][args]                    

                for args in settings[key]:
                    if key == "interfaces":
                        self.check_interface(args)
                        self.__interface(True, zone, args)
                    elif key == "icmp_blocks":
                        self.check_icmp_block(*args)
                        self.__icmp_block(True, zone, *args)
                    elif key == "forward_ports":
                        self.check_forward_port(*args)
                        mark = settings[key][args]["mark"]
                        self.__forward_port(True, zone, *args, mark_id=mark)
                    elif key == "service":
                        self.check_service(args)
                        self.__service(True, zone, args)
                    elif key == "port":
                        self.check_port(*args)
                        self.__port(True, zone, *args)
                    elif key == "masquerade":
                        self.__masquerade(True, zone)
                    else:
                        log.error("Zone '%s': Unknown setting '%s:%s', "
                                  "unable to restore.", zone, key, args)
        except FirewallError, msg:
            log.error(msg)

    # INTERFACES

    def check_interface(self, interface):
        self._fw.check_interface(interface)

    def __interface_id(self, interface):
        self.check_interface(interface)
        return interface

    def __interface(self, enable, zone, interface):
        table = "filter"
        rules = [ ]
        for ipv in [ "ipv4", "ipv6" ]:
            for chain in [ "INPUT", "FORWARD_IN", "FORWARD_OUT" ]:
                # create needed chains if not done already
                if enable:
                    self.add_chain(zone, table, chain)

                # handle trust and block zone directly, accept or reject
                # others will be placed into the proper zone chains
                opt = INTERFACE_ZONE_OPTS[chain]
                src_chain = INTERFACE_ZONE_SRC[chain]
                target = self._zones[zone].target.format(
                    chain=SHORTCUTS[chain], zone=zone)
                rules.append((ipv, [ "%s_ZONES" % src_chain, "-t", table,
                                     opt, interface, "-j", target ]))

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret:
            (cleanup_rules, msg) = ret
            self._fw.handle_rules(cleanup_rules, not enable)
            log.debug2(msg)
            if enable:
                raise FirewallError(ADD_FAILED)
            else:
                raise FirewallError(REMOVE_FAILED)

        if not enable:
            self.remove_chain(zone, table, chain)

    def add_interface(self, zone, interface, timeout=0, sender=None):
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        interface_id = self.__interface_id(interface)

        if interface_id in _obj.interfaces:
            raise FirewallError(ZONE_ALREADY_SET)
        if self.get_zone_of_interface(interface) != None:
            raise FirewallError(ZONE_CONFLICT)

        self.__interface(True, _zone, interface)

        _obj.interfaces.append(interface)
        _obj.settings["interfaces"][interface_id] = \
            self.__gen_settings(timeout, sender)

        return _zone

    def remove_interface(self, zone, interface):
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        interface_id = self.__interface_id(interface)
        if interface_id not in _obj.interfaces:
            zoi = self.get_zone_of_interface(interface)
            if zoi == None:
                raise FirewallError(UNKNOWN_INTERFACE)
            if zoi != _zone:
                raise FirewallError(ZONE_CONFLICT)

        self.__interface(False, _zone, interface)

        _obj.interfaces.remove(interface)
        if interface_id in _obj.settings:
            del _obj.settings["interfaces"][interface_id]

        return _zone

    def query_interface(self, zone, interface):
        self._fw.check_interface(interface)
        return self.__interface_id(interface) in self.get_zone(zone).interfaces

    def get_interfaces(self, zone):
        return self.get_zone(zone).interfaces

    def get_zone_of_interface(self, interface):
        self.check_interface(interface)
        for zone in self._zones:
            if interface in self._zones[zone].interfaces:
                # an interface can only be part of one zone
                return zone
        return None

    # SERVICES

    def check_service(self, service):
        self._fw.check_service(service)

    def __service_id(self, service):
        self.check_service(service)
        return service

    def __service(self, enable, zone, service):
        svc = self._fw.service.get_service(service)

        if enable:
            self.add_chain(zone, "filter", "INPUT")

        rules = [ ]
        for ipv in [ "ipv4", "ipv6" ]:
            # handle rules
            for (port,proto) in svc.ports:
                target = self._zones[zone].target.format(
                    chain=SHORTCUTS["INPUT"], zone=zone)
                rule = [ "%s_allow" % (target), "-t", "filter" ]
                if proto in [ "tcp", "udp" ]:
                    rule += [ "-m", proto, "-p", proto ]
                else:
                    if ipv == "ipv4":
                         rule += [ "-p", proto ]
                    else:
                         rule += [ "-m", "ipv6header", "--header", proto ]
                if port:
                     rule += [ "--dport", "%s" % portStr(port) ]
                if ipv in svc.destination:
                     rule += [ "-d",  svc.destination[ipv] ]
                rule += [ "-j", "ACCEPT" ]
                rules.append((ipv, rule))

        cleanup_rules = None
        cleanup_modules = None
        msg = None

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret == None: # no error, handle modules
            mod_ret = self._fw.handle_modules(svc.modules, enable)
            if mod_ret != None: # error loading modules
                (cleanup_modules, msg) = mod_ret
                cleanup_rules = rules
        else: # ret != None
            (cleanup_rules, msg) = ret

        if cleanup_rules!= None or cleanup_modules != None:
            if cleanup_rules:
                self._fw.handle_rules(cleanup_rules, not enable)
            if cleanup_modules:
                self._fw.handle_modules(cleanup_modules, not enable)
            # TODO: log msg
            if enable:
                raise FirewallError(ENABLE_FAILED)
            else:
                raise FirewallError(DISABLE_FAILED)

        if not enable:
            self.remove_chain(zone, "filter", "INPUT")

    def add_service(self, zone, service, timeout=0, sender=None):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        service_id = self.__service_id(service)
        if service_id in _obj.services:
            raise FirewallError(ALREADY_ENABLED)

        self.__service(True, _zone, service)

        _obj.services.append(service_id)
        _obj.settings["services"][service_id] = \
            self.__gen_settings(timeout, sender)

        return _zone

    def remove_service(self, zone, service):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        service_id = self.__service_id(service)
        if not service_id in _obj.services:
            raise FirewallError(NOT_ENABLED)

        self.__service(False, _zone, service)

        _obj.services.remove(service_id)
        if service_id in _obj.settings["services"]:
            del _obj.settings["services"][service_id]

        return _zone

    def query_service(self, zone, service):
        return (self.__service_id(service) in self.get_zone(zone).services)

    def get_services(self, zone):
        return self.get_zone(zone).services

    # PORTS

    def check_port(self, port, protocol):
        self._fw.check_port(port)
        self._fw.check_protocol(protocol)        

    def __port_id(self, port, protocol):
        self.check_port(port, protocol)
        return (portStr(port, "-"), protocol)

    def __port(self, enable, zone, port, protocol):
        if enable:
            self.add_chain(zone, "filter", "INPUT")

        rules = [ ]
        for ipv in [ "ipv4", "ipv6" ]:
            target = self._zones[zone].target.format(chain=SHORTCUTS["INPUT"],
                                                     zone=zone)
            rules.append((ipv, [ "%s_allow" % (target),
                                 "-t", "filter",
                                 "-m", protocol, "-p", protocol,
                                 "--dport", portStr(port),
                                 "-j", "ACCEPT" ]))

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret:
            (cleanup_rules, msg) = ret
            self._fw.handle_rules(cleanup_rules, not enable)
            # TODO: log , port_str, str(msg))
            if enable:
                raise FirewallError(ENABLE_FAILED)
            else:
                raise FirewallError(DISABLE_FAILED)
        
        if not enable:
            self.remove_chain(zone, "filter", "INPUT")

    def add_port(self, zone, port, protocol, timeout=0, sender=None):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        port_id = self.__port_id(port, protocol)
        if port_id in _obj.ports:
            raise FirewallError(ALREADY_ENABLED)

        self.__port(True, _zone, port, protocol)

        _obj.ports.append(port_id)
        _obj.settings["ports"][port_id] = \
            self.__gen_settings(timeout, sender)

        return _zone

    def remove_port(self, zone, port, protocol):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        port_id = self.__port_id(port, protocol)
        if not port_id in _obj.ports:
            raise FirewallError(NOT_ENABLED)

        self.__port(False, _zone, port, protocol)

        _obj.ports.remove(port_id)
        if port_id in _obj.settings["ports"]:
            del _obj.settings["ports"][port_id]

        return _zone

    def query_port(self, zone, port, protocol):
        return self.__port_id(port, protocol) in self.get_zone(zone).ports

    def get_ports(self, zone):
        return self.get_zone(zone).ports

    # MASQUERADE

    def __masquerade_id(self):
        return True

    def __masquerade(self, enable, zone):
        if enable:
            self.add_chain(zone, "nat", "POSTROUTING")
            self.add_chain(zone, "filter", "FORWARD_OUT")

        rules = [ ]
        for ipv in [ "ipv4" ]: # IPv4 only!
            target = self._zones[zone].target.format(
                chain=SHORTCUTS["POSTROUTING"], zone=zone)
            rules.append((ipv, [ "%s_allow" % (target),
                                 "-t", "nat", "-j", "MASQUERADE" ]))
            # FORWARD_OUT
            target = self._zones[zone].target.format(
                chain=SHORTCUTS["FORWARD_OUT"], zone=zone)
            rules.append((ipv, [ "%s_allow" % (target),
                                 "-t", "filter", "-j", "ACCEPT" ]))

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret:
            (cleanup_rules, msg) = ret
            self._fw.handle_rules(cleanup_rules, not enable)
            # TODO: log msg
            if enable:
                raise FirewallError(ENABLE_FAILED)
            else:
                raise FirewallError(DISABLE_FAILED)

        if not enable:
            self.remove_chain(zone, "nat", "POSTROUTING")
            self.remove_chain(zone, "filter", "FORWARD_OUT")

    def enable_masquerade(self, zone, timeout, sender):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        masquerade_id = self.__masquerade_id()
        if masquerade_id == _obj.masquerade:
            raise FirewallError(ALREADY_ENABLED)

        self.__masquerade(True, _zone)

        _obj.masquerade = masquerade_id
        _obj.settings["masquerade"][masquerade_id] = \
            self.__gen_settings(timeout, sender)

        return _zone

    def disable_masquerade(self, zone):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        masquerade_id = self.__masquerade_id()
        if masquerade_id != _obj.masquerade:
            raise FirewallError(NOT_ENABLED)

        self.__masquerade(False, _zone)

        _obj.masquerade = not masquerade_id
        if masquerade_id in _obj.settings["masquerade"]:
            del _obj.settings["masquerade"][masquerade_id]

        return _zone

    def query_masquerade(self, zone):
        return self.__masquerade_id() == self.get_zone(zone).masquerade

    # PORT FORWARDING

    def check_forward_port(self, port, protocol, toport=None, toaddr=None):
        self._fw.check_port(port)
        self._fw.check_protocol(protocol)
        if toport:
            self._fw.check_port(toport)
        if toaddr:
            self._fw.check_ip(toaddr)
        if not toport and not toaddr:
            raise FirewallError(INVALID_FORWARD)

    def __forward_port_id(self, port, protocol, toport=None, toaddr=None):
        self.check_forward_port(port, protocol, toport, toaddr)
        return (portStr(port, "-"), protocol,
                portStr(toport, "-"), str(toaddr))

    def __forward_port(self, enable, zone, port, protocol, toport=None,
                       toaddr=None, mark_id=None):
        mark_str = "0x%x" % mark_id
        port_str = portStr(port)

        dest = [ ]
        to = ""
        if toaddr:
            to += toaddr

        if toport and toport != "":
            toport_str = portStr(toport)
            dest = [ "--dport", toport_str ]
            to += ":%s" % portStr(toport, "-")

        mark = [ "-m", "mark", "--mark", mark_str ]

        if enable:
            self.add_chain(zone, "mangle", "PREROUTING")
            self.add_chain(zone, "nat", "PREROUTING")
            if not toaddr:
                self.add_chain(zone, "filter", "INPUT")
            else:
                self.add_chain(zone, "filter", "FORWARD_IN")

        rules = [ ]
        for ipv in [ "ipv4" ]: # IPv4 only!
            target = self._zones[zone].target.format(
                chain=SHORTCUTS["PREROUTING"], zone=zone)
            rules.append((ipv, [ "%s_allow" % (target),
                                 "-t", "mangle",
                                 "-p", protocol, "--dport", port_str,
                                 "-j", "MARK", "--set-mark", mark_str ]))
            # local and remote
            rules.append((ipv, [ "%s_allow" % (target),
                                 "-t", "nat",
                                 "-p", protocol ] + mark + \
                              [ "-j", "DNAT", "--to-destination", to ]))

            if not toaddr:
                # local only
                target = self._zones[zone].target.format(
                    chain=SHORTCUTS["INPUT"], zone=zone)
                rules.append((ipv, [ "%s_allow" % (target),
                                     "-t", "filter" ] + \
                                  mark + [ "-j", "ACCEPT" ]))
            else:
                # FORWARD_IN
                target = self._zones[zone].target.format(
                    chain=SHORTCUTS["FORWARD_IN"], zone=zone)
                rules.append((ipv, [ "%s_allow" % (target),
                                     "-t", "filter" ] + \
                                  mark + [ "-j", "ACCEPT" ]))

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret:
            (cleanup_rules, msg) = ret
            self._fw.handle_rules(cleanup_rules, not enable)
            # TODO: log msg
            if enable:
                self._fw.del_mark(mark_id)
                raise FirewallError(ENABLE_FAILED)
            else:
                raise FirewallError(DISABLE_FAILED)

        if not enable:
            self.remove_chain(zone, "mangle", "PREROUTING")
            self.remove_chain(zone, "nat", "PREROUTING")
            if not toaddr:
                self.remove_chain(zone, "filter", "INPUT")
            else:
                self.remove_chain(zone, "filter", "FORWARD_IN")

    def add_forward_port(self, zone, port, protocol, toport=None,
                         toaddr=None, timeout=0, sender=None):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        forward_id = self.__forward_port_id(port, protocol, toport, toaddr)
        if forward_id in _obj.forward_ports:
            raise FirewallError(ALREADY_ENABLED)

        mark = self._fw.new_mark()
        self.__forward_port(True, _zone, port, protocol, toport, toaddr,
                            mark_id=mark)
        
        _obj.forward_ports.append(forward_id)
        _obj.settings["forward_ports"][forward_id] = \
            self.__gen_settings(timeout, sender, mark=mark)

        return _zone

    def remove_forward_port(self, zone, port, protocol, toport=None,
                            toaddr=None):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        forward_id = self.__forward_port_id(port, protocol, toport, toaddr)
        if not forward_id in _obj.forward_ports:
            raise FirewallError(NOT_ENABLED)

        mark = _obj.settings["forward_ports"][forward_id]["mark"]

        self.__forward_port(False, _zone, port, protocol, toport, toaddr,
                            mark_id=mark)

        _obj.forward_ports.remove(forward_id)
        if forward_id in _obj.settings["forward_ports"]:
            del _obj.settings["forward_ports"][forward_id]
        self._fw.del_mark(mark)

        return _zone

    def query_forward_port(self, zone, port, protocol, toport=None,
                           toaddr=None):
        forward_id = self.__forward_port_id(port, protocol, toport, toaddr)
        return forward_id in self.get_zone(zone).forward_ports

    def get_forward_ports(self, zone):
        return self.get_zone(zone).forward_ports

    # ICMP BLOCK

    def check_icmp_block(self, icmp):
        self._fw.check_icmp_type(icmp)

    def __icmp_block_id(self, icmp):
        self.check_icmp_block(icmp)
        return icmp

    def __icmp_block(self, enable, zone, icmp):
        ict = self._fw.icmptype.get_icmptype(icmp)

        if enable:
            self.add_chain(zone, "filter", "INPUT")
            self.add_chain(zone, "filter", "FORWARD_IN")

        rules = [ ]
        for ipv in [ "ipv4", "ipv6" ]:
            if ict.destination and ipv not in ict.destination:
                continue

            if ipv == "ipv4":
                proto = [ "-p", "icmp" ]
                match = [ "-m", "icmp", "--icmp-type", icmp ]
            else:
                proto = [ "-p", "ipv6-icmp" ]
                match = [ "-m", "icmp6", "--icmpv6-type", icmp ]

            target = self._zones[zone].target.format(chain=SHORTCUTS["INPUT"],
                                                     zone=zone)
            rules.append((ipv, [ "%s_deny" % (target),
                                 "-t", "filter", ] + proto + \
                              match + [ "-j", "%%REJECT%%" ]))
            target = self._zones[zone].target.format(
                chain=SHORTCUTS["FORWARD_IN"], zone=zone)
            rules.append((ipv, [ "%s_deny" % (target),
                                 "-t", "filter", ] + proto + \
                              match + [ "-j", "%%REJECT%%" ]))

        # handle rules
        ret = self._fw.handle_rules(rules, enable)
        if ret:
            (cleanup_rules, msg) = ret
            self._fw.handle_rules(cleanup_rules, not enable)
            # TODO: log msg
            if enable:
                raise FirewallError(ENABLE_FAILED)
            else:
                raise FirewallError(DISABLE_FAILED)

        if not enable:
            self.remove_chain(zone, "filter", "INPUT")
            self.remove_chain(zone, "filter", "FORWARD_IN")

    def add_icmp_block(self, zone, icmp, timeout, sender):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        icmp_id = self.__icmp_block_id(icmp)
        if icmp_id in _obj.icmp_blocks:
            raise FirewallError(ALREADY_ENABLED)

        self.__icmp_block(True, zone, icmp)

        _obj.icmp_blocks.append(icmp_id)
        _obj.settings["icmp_blocks"][icmp_id] = \
            self.__gen_settings(timeout, sender)

        return _zone

    def remove_icmp_block(self, zone, icmp):
        self.check_immutable(zone)
        self._fw.check_panic()
        _zone = self._fw.check_zone(zone)
        _obj = self._zones[_zone]

        icmp_id = self.__icmp_block_id(icmp)
        if not icmp_id in _obj.icmp_blocks:
            raise FirewallError(NOT_ENABLED)

        self.__icmp_block(False, zone, icmp)

        _obj.icmp_blocks.remove(icmp_id)
        if icmp_id in _obj.settings["icmp_blocks"]:
            del _obj.settings["icmp_blocks"][icmp_id]

        return _zone

    def query_icmp_block(self, zone, icmp):
        return self.__icmp_block_id(icmp) in self.get_zone(zone).icmp_blocks

    def get_icmp_blocks(self, zone):
        return self.get_zone(zone).icmp_blocks