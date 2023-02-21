#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application Menu class and helpers.
"""
# pylint: disable=import-error
import asyncio
import subprocess
import sys
from typing import Optional, Dict
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events

from .settings_page import SettingsPage
from .application_page import AppPage
from .search_page import SearchPage
from .desktop_file_manager import DesktopFileManager
from .favorites_page import FavoritesPage
from .custom_widgets import SelfAwareMenu
from .vm_manager import VMManager
from .page_handler import MenuPage

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-appmenu')


class AppMenu(Gtk.Application):
    """
    Main Gtk.Application for appmenu.
    """
    def __init__(self, qapp, dispatcher):
        """
        :param qapp: qubesadmin.Qubes object
        :param dispatcher: qubesadmin.vm.EventsDispatcher
        """
        super().__init__(application_id='org.qubesos.appmenu',
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,)
        self.qapp = qapp
        self.dispatcher = dispatcher
        self.primary = False
        self.keep_visible = False
        self.initial_page = 1
        self.start_in_background = False

        self._add_cli_options()

        self.builder: Optional[Gtk.Builder] = None
        self.main_window: Optional[Gtk.Window] = None
        self.main_notebook: Optional[Gtk.Notebook] = None

        self.fav_app_list: Optional[Gtk.ListBox] = None
        self.sys_tools_list: Optional[Gtk.ListBox] = None

        self.desktop_file_manager: Optional[DesktopFileManager] = None
        self.vm_manager: Optional[VMManager] = None

        self.handlers: Dict[str, MenuPage] = {}

        self.power_button: Optional[Gtk.Button] = None

        self.highlight_tag: Optional[str] = None

        self.tasks = []

    def _add_cli_options(self):
        self.add_main_option(
            "keep-visible",
            ord("k"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Do not hide the menu after action",
            None,
        )

        self.add_main_option(
            'page',
            ord('p'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.INT,
            "Open menu at selected page; 0 is the application page, 1 is the"
            "favorites page and 2 is the system tools page"
        )

        self.add_main_option(
            "background",
            ord("b"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Do not show the menu at start, run in the background; useful "
            "for initial autostart",
            None,
        )

    def do_command_line(self, command_line):
        """
        Handle CLI arguments. This method overrides default do_command_line
        from Gtk.Application (and due to pygtk being dynamically generated
        pylint is confused about its arguments).
        """
        # pylint: disable=arguments-differ
        Gtk.Application.do_command_line(self, command_line)
        options = command_line.get_options_dict()
        # convert GVariantDict -> GVariant -> dict
        options = options.end().unpack()

        if "keep-visible" in options:
            self.keep_visible = True
        if "page" in options:
            self.initial_page = options['page']
        if "background" in options:
            self.start_in_background = True
        self.activate()
        return 0

    @staticmethod
    def _do_power_button(_widget):
        """
        Run xfce4's default logout button. Possible enhancement would be
        providing our own tiny program.
        """
        # pylint: disable=consider-using-with
        subprocess.Popen('xfce4-session-logout', stdin=subprocess.DEVNULL)

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        if not self.primary:
            self.perform_setup()
            self.primary = True
            assert self.main_window
            if not self.start_in_background:
                self.main_window.show_all()
            self.initialize_state()
            # set size if too big
            current_height = self.main_window.get_allocated_height()
            max_height = self.main_window.get_screen().get_height() * 0.9
            if current_height > max_height:
                self.main_window.resize(self.main_window.get_allocated_width(),
                                        int(max_height))


            loop = asyncio.get_event_loop()
            self.tasks = [
                asyncio.ensure_future(self.dispatcher.listen_for_events()),
            ]

            loop.run_until_complete(asyncio.wait(
                self.tasks, return_when=asyncio.FIRST_EXCEPTION))

        else:
            if self.main_notebook:
                self.main_notebook.set_current_page(self.initial_page)
            if self.main_window:
                if self.main_window.is_visible() and not self.keep_visible:
                    self.main_window.hide()
                else:
                    self.main_window.present()

    def hide_menu(self):
        """
        Unless CLI options specified differently, the menu will try to hide
        itself. Should be called after all sorts of actions like running an
        app or clicking outside the menu.
        """
        # reset search tab
        self.handlers['search_page'].initialize_page()
        if not self.keep_visible and self.main_window:
            self.main_window.hide()

    def _key_press(self, _widget, event):
        """
        Keypress handler, to allow closing the menu with an ESC key
        """
        if event.keyval == Gdk.KEY_Escape:
            self.hide_menu()

    def _focus_out(self, _widget, _event: Gdk.EventFocus):
        """
        Hide the menu on focus out, unless a right-click menu is open
        """
        if SelfAwareMenu.OPEN_MENUS <= 0:
            self.hide_menu()

    def initialize_state(self):
        """
        Initial state, that is - menu is open at the 0th page and pages
        will initialize their state if needed. Separate function because
        some things (like widget size adjustments) must be called after
        widgets are realized and not on init.
        """
        if self.main_notebook:
            self.main_notebook.set_current_page(self.initial_page)
        for page in self.handlers.values():
            page.initialize_page()

    def perform_setup(self):
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        self.load_style()
        self.builder = Gtk.Builder()

        self.fav_app_list = self.builder.get_object('fav_app_list')
        self.sys_tools_list = self.builder.get_object('sys_tools_list')
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, 'qubes-menu.glade'))
        self.main_window = self.builder.get_object('main_window')
        self.main_notebook = self.builder.get_object('main_notebook')

        self.main_window.set_events(Gdk.EventMask.FOCUS_CHANGE_MASK)
        self.main_window.connect('focus-out-event', self._focus_out)
        self.main_window.connect('key_press_event', self._key_press)
        self.add_window(self.main_window)
        self.desktop_file_manager = DesktopFileManager(self.qapp)
        self.vm_manager = VMManager(self.qapp, self.dispatcher)

        self.handlers = {
            'search_page': SearchPage(self.vm_manager, self.builder,
                                      self.desktop_file_manager),
            'app_page': AppPage(self.vm_manager, self.builder,
                                self.desktop_file_manager),
            'favorites_page': FavoritesPage(self.qapp, self.builder,
                                            self.desktop_file_manager,
                                            self.dispatcher, self.vm_manager),
            'settings_page': SettingsPage(self.qapp, self.builder,
                                          self.desktop_file_manager,
                                          self.dispatcher)}
        self.power_button = self.builder.get_object('power_button')
        self.power_button.connect('clicked', self._do_power_button)
        self.main_notebook.connect('switch-page', self._handle_page_switch)
        self.connect('shutdown', self.do_shutdown)

        self.main_window.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.main_window.connect('key_press_event', self._key_pressed)

    def load_style(self):
        """Load appropriate CSS stylesheet and associated properties."""
        # TODO: this should be called and updated when style changes
        # from light to dark
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(pkg_resources.resource_filename(
            __name__, 'qubes-menu-dark.css'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        label = Gtk.Label()
        style_context: Gtk.StyleContext = label.get_style_context()
        style_context.add_class('search_highlight')
        bg_color = style_context.get_background_color(Gtk.StateType.NORMAL)
        fg_color = style_context.get_color(Gtk.StateType.NORMAL)

        # This converts a Gdk.RGBA color to a hex representation liked by span
        # tags in Pango
        self.highlight_tag = \
            f'<span background="{self._rgba_color_to_hex(bg_color)}" ' \
            f'color="{self._rgba_color_to_hex(fg_color)}">'

    @staticmethod
    def _rgba_color_to_hex(color: Gdk.RGBA):
        return '#' + ''.join([f'{int(c*255):0>2x}'
                              for c in (color.red, color.green, color.blue)])


    def _key_pressed(self, _widget, event_key: Gdk.EventKey):
        """If user presses a key that's not a navigation key, open
        Search. Nav keys are: arrows, esc, return, tab"""
        if event_key.keyval not in [Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left,
                                Gdk.KEY_Right, Gdk.KEY_Escape, Gdk.KEY_Return,
                                    Gdk.KEY_Tab]:
            search_page = self.handlers.get('search_page')

            if not isinstance(search_page, SearchPage):
                return False

            search_page.search_entry.grab_focus_without_selecting()

            if not self.main_notebook:
                return False
            if self.main_notebook.get_current_page() != 0:
                self.main_notebook.set_current_page(0)
            return False

        return False

    def _handle_page_switch(self, _widget, page, _page_num):
        """
        On page switch some things need to happen, mostly cleaning any old
        selections/menu options highlighted.
        """
        page_handler = self.handlers.get(page.get_name())
        if page_handler:
            page_handler.initialize_page()


def main():
    """
    Start the menu app
    """
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    app = AppMenu(qapp, dispatcher)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
