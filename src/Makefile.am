SUBDIRS = icons

dist_bin_SCRIPTS = firewall-applet firewall-cmd firewall-offline-cmd firewall-config
dist_sbin_SCRIPTS = firewalld

gladedir = $(pkgdatadir)
dist_glade_DATA = firewall-config.glade

gtkextradir = $(pkgdatadir)
dist_gtkextra_DATA = gtk3_chooserbutton.py

nobase_dist_python_DATA = \
	firewall/client.py \
	firewall/dbus_utils.py \
	firewall/errors.py \
	firewall/functions.py \
	firewall/fw_types.py \
	firewall/__init__.py \
	firewall/config/dbus.py \
	firewall/config/__init__.py \
	firewall/core/base.py \
	firewall/core/ebtables.py \
	firewall/core/fw_config.py \
	firewall/core/fw_direct.py \
	firewall/core/fw_icmptype.py \
	firewall/core/fw_policies.py \
	firewall/core/fw.py \
	firewall/core/fw_service.py \
	firewall/core/fw_test.py \
	firewall/core/fw_zone.py \
	firewall/core/__init__.py \
	firewall/core/io/direct.py \
	firewall/core/io/firewalld_conf.py \
	firewall/core/io/icmptype.py \
	firewall/core/io/__init__.py \
	firewall/core/io/io_object.py \
	firewall/core/io/lockdown_whitelist.py \
	firewall/core/io/service.py \
	firewall/core/io/zone.py \
	firewall/core/ipXtables.py \
	firewall/core/logger.py \
	firewall/core/modules.py \
	firewall/core/prog.py \
	firewall/core/rich.py \
	firewall/core/watcher.py \
	firewall/server/config_icmptype.py \
	firewall/server/config.py \
	firewall/server/config_service.py \
	firewall/server/config_zone.py \
	firewall/server/decorators.py \
	firewall/server/firewalld.py \
	firewall/server/__init__.py \
	firewall/server/server.py

EXTRA_DIST = \
	firewall/config/__init__.py.in

CLEANFILES = *~ *\# .\#* *.py?

install-data-local:
	@echo "Fixing python shebang"
	@list='$(dist_bin_SCRIPTS)'; \
	for p in $$list; do \
	  echo $(top_srcdir)/fix_python_shebang.sh "$(DESTDIR)$(bindir)/$$p"; \
	  $(top_srcdir)/fix_python_shebang.sh "$(DESTDIR)$(bindir)/$$p"; \
	done
	@list='$(dist_sbin_SCRIPTS)'; \
	for p in $$list; do \
	  echo $(top_srcdir)/fix_python_shebang.sh "$(DESTDIR)$(sbindir)/$$p"; \
	  $(top_srcdir)/fix_python_shebang.sh "$(DESTDIR)$(sbindir)/$$p"; \
	done
