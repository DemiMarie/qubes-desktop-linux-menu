# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2021 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
"""
Various custom Gtk widgets used in Qubes App Menu.
"""
import subprocess

from . import constants
from .utils import load_icon
from .vm_manager import VMEntry

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango


class LimitedWidthLabel(Gtk.Label):
    """
    Gtk.Label, but with ellipsization and capped at 35 characters wide
    (which is not coincidentally 4 characters more than maximum VM name length)
    """
    def __init__(self, label_text=None):
        """
        :param label_text: optional text of the newly instantiated label
        """
        super().__init__()
        if label_text:
            self.set_label(label_text)
        self.set_width_chars(35)
        self.set_xalign(0)
        self.set_ellipsize(Pango.EllipsizeMode.END)


class HoverEventBox(Gtk.EventBox):
    """An EventBox that grabs provided widget on mouse hover."""
    def __init__(self, focus_widget: Gtk.Widget):
        super().__init__()
        self.mouse = False
        self.focus_widget = focus_widget

        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.add_events(Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect('enter-notify-event', self._enter_event)
        self.connect('leave-notify-event', self._leave_event)

    def _enter_event(self, *_args):
        self.mouse = True
        GLib.timeout_add(constants.HOVER_TIMEOUT, self._select_me)

    def _leave_event(self, *_args):
        self.mouse = False

    def _select_me(self, *_args):
        if not self.mouse:
            return False
        self.focus_widget.grab_focus()
        return True


class HoverListBox(Gtk.ListBoxRow):
    """
    Gtk.ListBoxRow, but selects itself on hover (after a timeout specified in
    constants.py)
    """
    def __init__(self):
        super().__init__()
        self.mouse = False
        self.event_box = HoverEventBox(focus_widget=self)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.event_box.add(self.main_box)
        self.add(self.event_box)

        self.connect('focus-in-event', self._on_focus)

    def _on_focus(self, *_args):
        if self.get_mapped():
            self.activate()
            self.get_parent().select_row(self)


class SelfAwareMenu(Gtk.Menu):
    """
    Gtk.Menu, but the class has a counter of number of currently opened menus.
    """
    OPEN_MENUS = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.get_style_context().add_class('right_menu')
        self.connect('realize', self._add_to_open)
        self.connect('deactivate', self._remove_from_open)

    @staticmethod
    def _add_to_open(*_args):
        SelfAwareMenu.OPEN_MENUS += 1

    @staticmethod
    def _remove_from_open(*_args):
        SelfAwareMenu.OPEN_MENUS -= 1


class NetworkIndicator(Gtk.Box):
    """
    Network Indicator Gtk.Box - changes appearance when set_network_state is
    called.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.icon_size = Gtk.IconSize.LARGE_TOOLBAR
        self.network_on: Gtk.Image = Gtk.Image.new_from_pixbuf(
            load_icon('qappmenu-networking-yes', self.icon_size))
        self.network_off: Gtk.Image = Gtk.Image.new_from_pixbuf(
            load_icon('qappmenu-networking-no', self.icon_size))

        _, height, _ = Gtk.icon_size_lookup(self.icon_size)
        self.network_on.set_size_request(-1, height * 1.3)
        self.network_off.set_size_request(-1, height * 1.3)

        self.pack_end(self.network_on, False, True, 10)
        self.pack_end(self.network_off, False, True, 10)

        self.network_on.set_tooltip_text('Qube is networked')
        self.network_off.set_tooltip_text('Qube is not networked')

        self.network_on.set_no_show_all(True)
        self.network_off.set_no_show_all(True)

        self.get_style_context().add_class('network_indicator')

    def set_network_state(self, state: bool):
        """
        :param state: boolean, True indicates network is on and False indicates
        it is off
        """
        self.set_visible(True)
        self.network_on.set_visible(state)
        self.network_off.set_visible(not state)


class SettingsEntry(Gtk.ListBoxRow):
    """
    Gtk.ListBoxRow especially for a (run VM) Settings entry.
    """
    def __init__(self):
        super().__init__()
        self.event_box = HoverEventBox(focus_widget=self)
        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.event_box.add(self.hbox)
        self.settings_icon = Gtk.Image.new_from_pixbuf(
            load_icon('qappmenu-settings'))
        self.hbox.pack_start(self.settings_icon, False, False, 5)
        self.settings_label = Gtk.Label(label="Settings", xalign=0)
        self.hbox.pack_start(self.settings_label, False, False, 5)
        self.get_style_context().add_class('app_entry')
        self.add(self.event_box)
        self.show_all()

    def run_app(self, vm):
        """Run settings for specified vm."""
        # pylint: disable=consider-using-with
        subprocess.Popen(
            ['qubes-vm-settings', vm.name], stdin=subprocess.DEVNULL)
        self.get_toplevel().get_application().hide_menu()

class VMRow(HoverListBox):
    """
    Helper widget representing a VM row.
    """
    def __init__(self, vm_entry: VMEntry):
        """
        :param vm_entry: VMEntry object, stored and managed by VMManager
        """
        super().__init__()
        self.vm_entry = vm_entry
        self.vm_name = vm_entry.vm_name
        self.get_style_context().add_class('vm_entry')

        self.icon_img = Gtk.Image()

        # add the icon for dispvm parent existing
        if self.vm_entry.parent_vm:
            self.dispvm_icon = Gtk.Image()
            dispvm_icon_img = load_icon('qappmenu-dispvm-child', None, 15)
            self.dispvm_icon.set_from_pixbuf(dispvm_icon_img)
            self.dispvm_icon.get_style_context().add_class('dispvm_icon')
            self.dispvm_icon.set_valign(Gtk.Align.START)
            self.main_box.pack_start(self.dispvm_icon, False, False, 2)

        self.main_box.pack_start(self.icon_img, False, False, 2)
        self.label = Gtk.Label(label=self.vm_entry.vm_name)
        self.main_box.pack_start(self.label, False, False, 2)

        self.update_contents(update_power_state=True, update_label=True,
                             update_has_network=True, update_type=True)

    def update_style(self, update_power_state: bool = True):
        """Update own style, based on whether VM is running or not and
        what type it has."""
        style_context: Gtk.StyleContext = self.get_style_context()
        if self.vm_entry.is_dispvm_template:
            style_context.add_class('dvm_template_entry')
        elif self.vm_entry.parent_vm:
            # has a parent VM means that it should have arrow etc.
            style_context.add_class('dispvm_entry')
        else:
            style_context.remove_class('dispvm_entry')
            style_context.remove_class('dvm_template_entry')

        if update_power_state:
            if self.vm_entry.power_state == 'Running':
                style_context.add_class('running_vm')
            else:
                style_context.remove_class('running_vm')

    def update_contents(self,
                        update_power_state=False,
                        update_label=False,
                        update_has_network=False,
                        update_type=False):
        """
        Update own contents (or related widgets, if applicable) based on state
        change.
        :param update_power_state: whether to update if VM is running or not
        :param update_label: whether label (vm icon) should be updated
        :param update_has_network: whether VM networking state should be
        updated
        :param update_type: whether VM type should be updated
        :return:
        """
        if update_label:
            icon_vm = load_icon(self.vm_entry.vm_icon_name)
            self.icon_img.set_from_pixbuf(icon_vm)
        if update_type or update_power_state:
            self.update_style(update_power_state)
            if self.get_parent():
                self.get_parent().invalidate_sort()
                self.get_parent().invalidate_filter()
                self.get_parent().select_row(None)
        if update_has_network:
            if self.is_selected() and self.get_parent():
                self.get_parent().select_row(None)
                self.get_parent().select_row(self)
        self.main_box.show_all()

    @property
    def sort_order(self):
        """
        Helper property exposing desired sort order.
        """
        return self.vm_entry.sort_name


class SearchVMRow(VMRow):
    """VM Row used for the Search tab."""
    def update_contents(self,
                        update_power_state=False,
                        update_label=False,
                        update_has_network=False,
                        update_type=False):
        """
        Search rows do not show power state.
        """
        super().update_contents(update_power_state=False,
                                update_label=update_label,
                                update_has_network=False,
                                update_type=update_type)


class AnyVMRow(HoverListBox):
    """Generic Any VM row for search purposes."""
    def __init__(self):
        super().__init__()
        self.vm_name = None
        self.sort_order = ''
        self.get_style_context().add_class('vm_entry')

        icon_img = Gtk.Image()
        icon_vm = load_icon('qubes-logo-icon')
        icon_img.set_from_pixbuf(icon_vm)
        self.main_box.pack_start(icon_img, False, False, 2)

        self.label = Gtk.Label()
        self.label.set_markup('<b>Any qube</b>')
        self.main_box.pack_start(self.label, False, False, 2)
        self.show_all()
