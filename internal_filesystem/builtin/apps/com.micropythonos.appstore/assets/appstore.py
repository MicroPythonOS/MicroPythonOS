import lvgl as lv
import json
import requests
import gc
import os
import time
import _thread

try:
    import zipfile
except ImportError:
    print("import zipfile failed, installation won't work!")

from mpos.apps import Activity, Intent
import mpos.ui

class AppStore(Activity):
    apps = []
    app_index_url = "https://apps.micropythonos.com/app_index.json"
    can_check_network = True

    # Widgets:
    main_screen = None
    update_button = None
    install_button = None
    install_label = None
    please_wait_label = None
    progress_bar = None

    def onCreate(self):
        self.main_screen = lv.obj()
        self.please_wait_label = lv.label(self.main_screen)
        self.please_wait_label.set_text("Downloading app index...")
        self.please_wait_label.center()
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        if len(self.apps):
            return
        try:
            import network
        except Exception as e:
            self.can_check_network = False
        if self.can_check_network and not network.WLAN(network.STA_IF).isconnected():
            self.please_wait_label.set_text("Error: WiFi is not connected.")
        else:
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.download_app_index, (self.app_index_url,))

    def download_app_index(self, json_url):
        try:
            response = requests.get(json_url, timeout=10)
        except Exception as e:
            print("Download failed:", e)
            lv.async_call(lambda l, error=e: self.please_wait_label.set_text(f"Downloading app index from:\n{json_url}\ngot error: {error}"), None)
            return
        if response and response.status_code == 200:
            #print(f"Got response text: {response.text}")
            try:
                applist = json.loads(response.text)
                for app in json.loads(response.text):
                    try:
                        self.apps.append(mpos.apps.App(**app))
                    except Exception as e:
                        print(f"Warning: could not add app from {json_url} to apps list: {e}")
                # Remove duplicates based on app.name
                seen = set()
                self.apps = [app for app in self.apps if not (app.name in seen or seen.add(app.name))]
                # Sort apps by app.name
                self.apps.sort(key=lambda x: x.name.lower())  # Use .lower() for case-insensitive sorting
                time.sleep_ms(200)
                lv.async_call(lambda l: self.please_wait_label.add_flag(lv.obj.FLAG.HIDDEN), None)
                lv.async_call(lambda l: self.create_apps_list(), None)
            except Exception as e:
                print(f"ERROR: could not parse reponse.text JSON: {e}")
            finally:
                response.close()

    def create_apps_list(self):
        print("create_apps_list")
        default_icon_dsc = self.load_icon("builtin/res/mipmap-mdpi/default_icon_64x64.png")
        apps_list = lv.list(self.main_screen)
        apps_list.set_style_border_width(0, 0)
        apps_list.set_style_radius(0, 0)
        apps_list.set_style_pad_all(0, 0)
        apps_list.set_size(lv.pct(100), lv.pct(100))
        print("create_apps_list iterating")
        for app in self.apps:
            item = apps_list.add_button(None, "Test")
            item.set_style_pad_all(0, 0)
            #item.set_style_border_width(0, 0)
            #item.set_style_radius(0, 0)
            item.set_size(lv.pct(100), lv.SIZE_CONTENT)
            item.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            cont = lv.obj(item)
            cont.set_style_pad_all(0, 0)
            cont.set_flex_flow(lv.FLEX_FLOW.ROW)
            cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
            cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            cont.set_style_border_width(0, 0)
            cont.set_style_radius(0, 0)
            cont.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            icon_spacer = lv.image(cont)
            icon_spacer.set_size(64, 64)
            app.image = icon_spacer
            icon_spacer.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            label_cont = lv.obj(cont)
            label_cont.set_style_border_width(0, 0)
            label_cont.set_style_radius(0, 0)
            label_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            label_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
            label_cont.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            name_label = lv.label(label_cont)
            name_label.set_text(app.name)
            name_label.set_style_text_font(lv.font_montserrat_16, 0)
            name_label.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            desc_label = lv.label(label_cont)
            desc_label.set_text(app.short_description)
            desc_label.set_style_text_font(lv.font_montserrat_12, 0)
            desc_label.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
        print("create_apps_list app done")
        try:
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.download_icons,())
        except Exception as e:
            print("Could not start thread to download icons: ", e)
    
    def download_icons(self):
        for app in self.apps:
            if app.image_dsc:
                print(f"Skipping icon download for {app.name} because already downloaded.")
                continue
            print(f"Downloading icon for {app.name}")
            image_dsc = self.download_icon(app.icon_url)
            app.image_dsc = image_dsc # save it for the app detail page
            lv.async_call(lambda l: app.image.set_src(image_dsc), None)
            time.sleep_ms(200) # not waiting here will result in some async_calls() not being executed
        print("Finished downloading icons...")

    def show_app_detail(self, app):
        intent = Intent(activity_class=AppDetail)
        intent.putExtra("app", app)
        self.startActivity(intent)

    @staticmethod
    def download_icon(url):
        print(f"Downloading icon from {url}")
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                image_data = response.content
                print("Downloaded image, size:", len(image_data), "bytes")
                image_dsc = lv.image_dsc_t({
                    'data_size': len(image_data),
                    'data': image_data
                })
                return image_dsc
            else:
                print("Failed to download image: Status code", response.status_code)
        except Exception as e:
            print(f"Exception during download of icon: {e}")
        return None

    @staticmethod
    def load_icon(icon_path):
        with open(icon_path, 'rb') as f:
            image_data = f.read()
            image_dsc = lv.image_dsc_t({
                'data_size': len(image_data),
                'data': image_data
            })
        return image_dsc

class AppDetail(Activity):

    action_label_install = "Install"
    action_label_uninstall = "Uninstall"
    action_label_restore = "Restore Built-in"
    action_label_nothing = "Disable" # This could mark builtin apps as "Disabled" somehow and also allow for "Enable" then

    # Widgets:
    install_button = None
    update_button = None
    progress_bar = None
    install_label = None

    def onCreate(self):
        print("Creating app detail screen...")
        app = self.getIntent().extras.get("app")
        app_detail_screen = lv.obj()
        app_detail_screen.set_style_pad_all(5, 0)
        app_detail_screen.set_size(lv.pct(100), lv.pct(100))
        app_detail_screen.set_pos(0, 40)
        app_detail_screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        #
        headercont = lv.obj(app_detail_screen)
        headercont.set_style_border_width(0, 0)
        headercont.set_style_pad_all(0, 0)
        headercont.set_flex_flow(lv.FLEX_FLOW.ROW)
        headercont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        headercont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        icon_spacer = lv.image(headercont)
        if app.image_dsc:
            icon_spacer.set_src(app.image_dsc)
        icon_spacer.set_size(64, 64)
        #
        detail_cont = lv.obj(headercont)
        detail_cont.set_style_border_width(0, 0)
        detail_cont.set_style_radius(0, 0)
        detail_cont.set_style_pad_all(0, 0)
        detail_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        detail_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
        name_label = lv.label(detail_cont)
        name_label.set_text(app.name)
        name_label.set_style_text_font(lv.font_montserrat_24, 0)
        publisher_label = lv.label(detail_cont)
        publisher_label.set_text(app.publisher)
        publisher_label.set_style_text_font(lv.font_montserrat_16, 0)
        #
        self.progress_bar = lv.bar(app_detail_screen)
        self.progress_bar.set_width(lv.pct(100))
        self.progress_bar.set_range(0, 100)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        # Always have this button:
        buttoncont = lv.obj(app_detail_screen)
        buttoncont.set_style_border_width(0, 0)
        buttoncont.set_style_radius(0, 0)
        buttoncont.set_style_pad_all(0, 0)
        buttoncont.set_flex_flow(lv.FLEX_FLOW.ROW)
        buttoncont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        buttoncont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        print(f"Adding (un)install button for url: {app.download_url}")
        self.install_button = lv.button(buttoncont)
        self.install_button.add_event_cb(lambda e, d=app.download_url, f=app.fullname: self.toggle_install(d,f), lv.EVENT.CLICKED, None)
        self.install_button.set_size(lv.pct(100), 40)
        self.install_label = lv.label(self.install_button)
        self.install_label.center()
        self.set_install_label(app.fullname)
        if self.is_update_available(app.fullname, app.version):
            self.install_button.set_size(lv.pct(47), 40) # make space for update button
            print("Update available, adding update button.")
            self.update_button = lv.button(buttoncont)
            self.update_button.set_size(lv.pct(47), 40)
            self.update_button.add_event_cb(lambda e, d=app.download_url, f=app.fullname: self.update_button_click(d,f), lv.EVENT.CLICKED, None)
            update_label = lv.label(self.update_button)
            update_label.set_text("Update")
            update_label.center()
        # version label:
        version_label = lv.label(app_detail_screen)
        version_label.set_width(lv.pct(100))
        version_label.set_text(f"Latest version: {app.version}") # make this bold if this is newer than the currently installed one
        version_label.set_style_text_font(lv.font_montserrat_12, 0)
        version_label.align_to(self.install_button, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        long_desc_label = lv.label(app_detail_screen)
        long_desc_label.align_to(version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        long_desc_label.set_text(app.long_description)
        long_desc_label.set_style_text_font(lv.font_montserrat_12, 0)
        long_desc_label.set_width(lv.pct(100))
        print("Loading app detail screen...")
        self.setContentView(app_detail_screen)
    

    def set_install_label(self, app_fullname):
        # Figure out whether to show:
        # - "install" option if not installed
        # - "update" option if already installed and new version
        # - "uninstall" option if already installed and not builtin
        # - "restore builtin" option if it's an overridden builtin app
        # So:
        # - install, uninstall and restore builtin can be same button, always shown
        # - update is separate button, only shown if already installed and new version
        is_installed = True
        update_available = False
        builtin_app = self.is_builtin_app(app_fullname)
        overridden_builtin_app = self.is_overridden_builtin_app(app_fullname)
        if not overridden_builtin_app:
            is_installed = AppDetail.is_installed_by_name(app_fullname)
        if is_installed:
            if builtin_app:
                if overridden_builtin_app:
                    action_label = self.action_label_restore
                else:
                    action_label = self.action_label_nothing
            else:
                action_label = self.action_label_uninstall
        else:
            action_label = self.action_label_install
        self.install_label.set_text(action_label)
    

    def toggle_install(self, download_url, fullname):
        print(f"Install button clicked for {download_url} and fullname {fullname}")
        label_text = self.install_label.get_text()
        if label_text == self.action_label_install:
            try:
                _thread.stack_size(mpos.apps.good_stack_size())
                _thread.start_new_thread(self.download_and_unzip, (download_url, f"apps/{fullname}", fullname))
            except Exception as e:
                print("Could not start download_and_unzip thread: ", e)
        elif label_text == self.action_label_uninstall or label_text == self.action_label_restore:
            print("Uninstalling app....")
            try:
                _thread.stack_size(mpos.apps.good_stack_size())
                _thread.start_new_thread(self.uninstall_app, (f"apps/{fullname}", fullname))
            except Exception as e:
                print("Could not start download_and_unzip thread: ", e)
    
    def update_button_click(self, download_url, fullname):
        print(f"Update button clicked for {download_url} and fullname {fullname}")
        self.update_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.install_button.set_size(lv.pct(100), 40)
        try:
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.download_and_unzip, (download_url, f"apps/{fullname}", fullname))
        except Exception as e:
            print("Could not start download_and_unzip thread: ", e)
    
    def uninstall_app(self, app_folder, app_fullname):
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...") # TODO: Put "Cancel" if cancellation is possible
        self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(33, lv.ANIM.ON)
        try:
            import shutil
            shutil.rmtree(app_folder)
            self.progress_bar.set_value(66, lv.ANIM.ON)
        except Exception as e:
            print(f"Removing app_folder {app_folder} got error: {e}")
        self.progress_bar.set_value(100, lv.ANIM.OFF)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(0, lv.ANIM.OFF)
        self.set_install_label(app_fullname)
        self.install_button.remove_state(lv.STATE.DISABLED)
        if self.is_builtin_app(app_fullname):
            self.update_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.install_button.set_size(lv.pct(47), 40) # if a builtin app was removed, then it was overridden, and a new version is available, so make space for update button
    

    def download_and_unzip(self, zip_url, dest_folder, app_fullname):
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...") # TODO: Put "Cancel" if cancellation is possible
        self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(20, lv.ANIM.ON)
        try:
            # Step 1: Download the .mpk file
            print(f"Downloading .mpk file from: {zip_url}")
            response = requests.get(zip_url, timeout=10)
            if response.status_code != 200:
                print("Download failed: Status code", response.status_code)
                response.close()
                self.set_install_label(app_fullname)
            self.progress_bar.set_value(40, lv.ANIM.ON)
            # Save the .mpk file to a temporary location
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass
            try:
                os.mkdir("tmp")
            except Exception:
                pass
            temp_zip_path = "tmp/temp.mpk"
            print(f"Writing to temporary mpk path: {temp_zip_path}")
            # TODO: check free available space first!
            with open(temp_zip_path, "wb") as f:
                f.write(response.content)
            self.progress_bar.set_value(60, lv.ANIM.ON)
            response.close()
            print("Downloaded .mpk file, size:", os.stat(temp_zip_path)[6], "bytes")
        except Exception as e:
            print("Download failed:", str(e))
            # Would be good to show error message here if it fails...
        finally:
            if 'response' in locals():
                response.close()
        try:
            # Step 2: Unzip the file
            print("Unzipping it to:", dest_folder)
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(dest_folder)
            self.progress_bar.set_value(80, lv.ANIM.ON)
            print("Unzipped successfully")
            # Step 3: Clean up
            os.remove(temp_zip_path)
            print("Removed temporary .mpk file")
        except Exception as e:
            print(f"Unzip and cleanup failed: {e}")
            # Would be good to show error message here if it fails...
        # Success:
        self.progress_bar.set_value(100, lv.ANIM.OFF)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(0, lv.ANIM.OFF)
        self.set_install_label(app_fullname)
        self.install_button.remove_state(lv.STATE.DISABLED)

    @staticmethod
    def compare_versions(ver1: str, ver2: str) -> bool:
        """Compare two version numbers (e.g., '1.2.3' vs '4.5.6').
        Returns True if ver1 is greater than ver2, False otherwise."""
        print(f"Comparing versions: {ver1} vs {ver2}")
        v1_parts = [int(x) for x in ver1.split('.')]
        v2_parts = [int(x) for x in ver2.split('.')]
        print(f"Version 1 parts: {v1_parts}")
        print(f"Version 2 parts: {v2_parts}")
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1 = v1_parts[i] if i < len(v1_parts) else 0
            v2 = v2_parts[i] if i < len(v2_parts) else 0
            print(f"Comparing part {i}: {v1} vs {v2}")
            if v1 > v2:
                print(f"{ver1} is greater than {ver2}")
                return True
            if v1 < v2:
                print(f"{ver1} is less than {ver2}")
                return False
        print(f"Versions are equal or {ver1} is not greater than {ver2}")
        return False

    @staticmethod
    def is_builtin_app(app_fullname):
        return AppDetail.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_overridden_builtin_app(app_fullname):
        return AppDetail.is_installed_by_path(f"apps/{app_fullname}") and AppDetail.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_update_available(app_fullname, new_version):
        appdir = f"apps/{app_fullname}"
        builtinappdir = f"builtin/apps/{app_fullname}"
        installed_app=None
        if AppDetail.is_installed_by_path(appdir):
            print(f"{appdir} found, getting version...")
            installed_app = mpos.apps.parse_manifest(f"{appdir}/META-INF/MANIFEST.JSON")
        elif AppDetail.is_installed_by_path(builtinappdir):
            print(f"{builtinappdir} found, getting version...")
            installed_app = mpos.apps.parse_manifest(f"{builtinappdir}/META-INF/MANIFEST.JSON")
        if not installed_app or installed_app.version == "0.0.0": # special case, if the installed app doesn't have a version number then there's no update
            return False
        return AppDetail.compare_versions(new_version, installed_app.version)

    @staticmethod
    def is_installed_by_path(dir_path):
        try:
            if os.stat(dir_path)[0] & 0x4000:
                print(f"is_installed_by_path: {dir_path} found, checking manifest...")
                manifest = f"{dir_path}/META-INF/MANIFEST.JSON"
                if os.stat(manifest)[0] & 0x8000:
                    return True
        except OSError:
            print(f"is_installed_by_path got OSError for {dir_path}")
            pass # Skip if directory or manifest doesn't exist
        return False

    @staticmethod
    def is_installed_by_name(app_fullname):
        print(f"Checking if app {app_fullname} is installed...")
        return AppDetail.is_installed_by_path(f"apps/{app_fullname}") or AppDetail.is_installed_by_path(f"builtin/apps/{app_fullname}")

