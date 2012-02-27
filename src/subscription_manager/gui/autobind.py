#
# GUI Module for the Autobind Wizard
#
# Copyright (c) 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import os
import gtk
import logging

import gettext
_ = gettext.gettext

log = logging.getLogger('rhsm-app.' + __name__)

from subscription_manager.cert_sorter import CertSorter
from subscription_manager.gui import widgets
from subscription_manager.gui.utils import GladeWrapper
from subscription_manager.gui.confirm_subs import ConfirmSubscriptionsScreen

DATA_PREFIX = os.path.dirname(__file__)
AUTOBIND_XML = GladeWrapper(os.path.join(DATA_PREFIX, "data/autobind.glade"))

CONFIRM_SUBS = 0
SELECT_SLA = 1

class DryRunResult(object):
    """ Encapsulates a dry-run autobind result from the server. """

    def __init__(self, service_level, server_json, cert_sorter):
        self.json = server_json
        self.sorter = cert_sorter
        self.service_level = service_level

    def covers_required_products(self):
        """
        Return True if this dry-run result would cover all installed
        products which are not covered by a valid entitlement.

        NOTE: we do not require full stacking compliance here. The server
        will return the best match it can find, but that may still leave you
        only partially entitled. We will still consider this situation a valid
        SLA to use, the key point being you have access to the content you
        need.
        """
        required_products = set(self.sorter.unentitled_products.keys())

        # The products that would be covered if we did this autobind:
        autobind_products = set()

        log.debug("Unentitled products: %s" % required_products)
        for pool_quantity in self.json:
            pool = pool_quantity['pool']
            # This is usually the MKT product and has no content, but it
            # doesn't hurt to include it:
            autobind_products.add(pool['productId'])
            for provided_prod in pool['providedProducts']:
                autobind_products.add(provided_prod['productId'])
        log.debug("Autobind would give access to: %s" % autobind_products)
        if required_products.issubset(autobind_products):
            log.debug("Found valid service level: %s" % self.service_level)
            return True
        else:
            log.debug("Service level does not cover required products: %s" % \
                    self.service_level)
            return False


class AutobindWizard(object):
    """
    Autobind Wizard: Manages screenflow used in several places in the UI.
    """

    def __init__(self, backend, consumer, facts):
        """
        Create the Autobind wizard.

        backend - A managergui.Backend object.
        consumer - A managergui.Consumer object.
        """
        log.debug("Launching autobind wizard.")
        self.backend = backend
        self.consumer = consumer
        self.facts = facts
        self.prod_dir = self.backend.product_dir
        self.ent_dir = self.backend.entitlement_dir

        self.owner_key = self.backend.uep.getOwner(
                self.consumer.getConsumerId())['key']

        # Using the current date time, we may need to expand this to work
        # with arbitrary dates for future entitling someday:
        # TODO: what if no products need entitlements?
        self.sorter = CertSorter(self.prod_dir, self.ent_dir,
                self.facts.get_facts())

        signals = {
        }

        AUTOBIND_XML.signal_autoconnect(signals)
        self.main_window = AUTOBIND_XML.get_widget("autobind_dialog")
        self.main_window.set_title(_("Subscribe System"))
        self.notebook = AUTOBIND_XML.get_widget("autobind_notebook")

        self._setup_screens()

        self._find_suitable_service_levels()

    def _find_suitable_service_levels(self):
        # Figure out what screen to display initially:
        # TODO: what if we already have an SLA selected?
        # TODO: test no SLA's available
        # TODO: test no results are returned for any SLA
        self.available_slas = self.backend.uep.getServiceLevelList(
                self.owner_key)
        log.debug("Available service levels: %s" % self.available_slas)
        # Will map service level (string) to the results of the dry-run
        # autobind results for each SLA that covers all installed products:
        self.suitable_slas = {}
        for sla in self.available_slas:
            dry_run_json = self.backend.uep.dryRunBind(self.consumer.uuid,
                    sla)
            log.debug("Dry run results: %s" % dry_run_json)
            dry_run = DryRunResult(sla, dry_run_json, self.sorter)
            log.debug(dry_run.covers_required_products())

    def _setup_screens(self):
        self.screens = {
                CONFIRM_SUBS: ConfirmSubscriptionsScreen(),
                SELECT_SLA: SelectSLAScreen(),
        }
        # TODO: this probably won't work, the screen flow is too conditional,
        # so we'll likely need to hard code the screens, and hook up logic
        # to the back button somehow

        # For each screen configured in this wizard, create a tab:
        for screen in self.screens.values():
            widget = screen.get_main_widget()
            widget.unparent()
            widget.reparent(self.notebook)
            self.notebook.append_page(widget)

    def show(self):
        self._load_initial_screen()
        self.main_window.show()

    def _load_initial_screen(self):
        available_sla = self._get_sla_data()

        next_screen = SELECT_SLA
        screen = self.screens[next_screen]
        self.notebook.set_page(next_screen)
        screen.load_data(available_sla)

    def _get_sla_data(self):
        owner = self.backend.uep.getOwner(self.consumer.getConsumerId())
        if not owner:
            return []

        possible_slas = self.backend.uep.getServiceLevelList(owner['key'])
        return possible_slas


class SelectSLAScreen(widgets.GladeWidget):
    """
    An autobind wizard screen that displays the  available
    SLAs that are provided by the installed products.
    """

    def __init__(self):
        widget_names = [
            'main_content',
            'detection_label',
            'detected_products_label',
            'product_list_label',
            'subscribe_all_as_label',
            'sla_radio_container'
        ]
        super(SelectSLAScreen, self).__init__('selectsla.glade', widget_names)

    def get_main_widget(self):
        """
        Returns the content wodget for this screen.
        """
        return self.main_content

    def load_data(self, available_sla):
        self._clear_buttons()
        group = None
        for sla in available_sla:
            radio = gtk.RadioButton(group = group, label = sla)
            self.sla_radio_container.pack_start(radio)
            radio.show()
            group = radio

    def _clear_buttons(self):
        child_widgets = self.sla_radio_container.get_children()
        for child in child_widgets:
            self.sla_radio_container.remove(child)

