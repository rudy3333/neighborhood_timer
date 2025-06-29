import requests
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
import os
import urllib.request
import tempfile
import threading
import time
import json
from datetime import datetime
import mimetypes
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

API_BASE = "https://adventure-time.hackclub.dev/api"
TOKEN_FILE = "auth_token.txt"
HACKATIME_KEY_FILE = "hackatime_api_key.txt"
OFFLINE_HEARTBEATS_DB = "offline_heartbeats.db"
SYNC_MAX_DEFAULT = 1000
SEND_LIMIT = 25
RATE_LIMIT_SECONDS = 120

class OfflineHeartbeatManager:
    def __init__(self):
        self.db_path = OFFLINE_HEARTBEATS_DB.replace('.db', '.json')
        self.last_sync_time = 0
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        """Initialize the JSON database for offline heartbeats"""
        try:
            if not os.path.exists(self.db_path):
                # Create initial structure mimicking BoltDB
                data = {
                    "heartbeats": {}
                }
                with open(self.db_path, 'w') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[OFFLINE] Error initializing database: {e}")
    
    def _load_data(self):
        """Load data from JSON file"""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"heartbeats": {}}
    
    def _save_data(self, data):
        """Save data to JSON file"""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[OFFLINE] Error saving data: {e}")
    
    def save_heartbeat_offline(self, heartbeat_data):
        """Save a heartbeat to offline storage using JSON file"""
        try:
            with self.lock:
                data = self._load_data()
                
                # Create a unique key based on timestamp and project
                timestamp = heartbeat_data.get('time', int(time.time()))
                project = heartbeat_data.get('project', 'unknown')
                key = f"{timestamp}-{project}"
                
                # Store heartbeat data
                data["heartbeats"][key] = heartbeat_data
                
                self._save_data(data)
                print(f"[OFFLINE] Saved heartbeat to offline storage: {key}")
                return True
        except Exception as e:
            print(f"[OFFLINE] Error saving heartbeat: {e}")
            return False
    
    def get_offline_heartbeats(self, limit=SYNC_MAX_DEFAULT):
        """Get heartbeats from offline storage"""
        try:
            with self.lock:
                data = self._load_data()
                heartbeats = []
                count = 0
                
                for key, heartbeat_data in data["heartbeats"].items():
                    if count >= limit:
                        break
                    heartbeats.append((key, heartbeat_data))
                    count += 1
                
                return heartbeats
        except Exception as e:
            print(f"[OFFLINE] Error getting offline heartbeats: {e}")
            return []
    
    def remove_heartbeat(self, key):
        """Remove a heartbeat from offline storage after successful sync"""
        try:
            with self.lock:
                data = self._load_data()
                if key in data["heartbeats"]:
                    del data["heartbeats"][key]
                    self._save_data(data)
                    print(f"[OFFLINE] Removed heartbeat: {key}")
        except Exception as e:
            print(f"[OFFLINE] Error removing heartbeat: {e}")
    
    def sync_offline_heartbeats(self, api_key):
        """Sync offline heartbeats to the API"""
        current_time = time.time()
        if current_time - self.last_sync_time < RATE_LIMIT_SECONDS:
            return  # Rate limiting
        
        heartbeats = self.get_offline_heartbeats()
        if not heartbeats:
            return
        
        print(f"[SYNC] Attempting to sync {len(heartbeats)} offline heartbeats")
        
        for key, heartbeat_data in heartbeats:
            try:
                # Ensure API key is current
                heartbeat_data['hackatimeToken'] = api_key
                
                response = requests.post(
                    f"{API_BASE}/heartbeats",
                    json=heartbeat_data,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                if response.status_code in (200, 202):
                    self.remove_heartbeat(key)
                    print(f"[SYNC] Successfully synced heartbeat {key}")
                else:
                    print(f"[SYNC] Failed to sync heartbeat {key}: {response.status_code}")
                
                time.sleep(0.1)  # Small delay between requests
                
            except Exception as e:
                print(f"[SYNC] Error syncing heartbeat {key}: {e}")
        
        self.last_sync_time = current_time

class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.email_input = TextInput(hint_text="Email address", multiline=False)
        self.layout.add_widget(self.email_input)
        self.otp_input = TextInput(hint_text="Enter OTP", multiline=False)
        self.otp_input.opacity = 0
        self.otp_input.disabled = True
        self.layout.add_widget(self.otp_input)
        self.error_label = Label(text="", color=(1,0,0,1))
        self.layout.add_widget(self.error_label)
        self.send_button = Button(text="Send OTP")
        self.send_button.bind(on_press=self.handle_send_otp)
        self.layout.add_widget(self.send_button)
        self.verify_button = Button(text="Verify", opacity=0, disabled=True)
        self.verify_button.bind(on_press=self.handle_verify_otp)
        self.layout.add_widget(self.verify_button)
        self.resend_button = Button(text="Resend OTP", opacity=0, disabled=True)
        self.resend_button.bind(on_press=self.handle_resend_otp)
        self.layout.add_widget(self.resend_button)
        self.add_widget(self.layout)

    def handle_send_otp(self, instance):
        self.error_label.text = ""
        email = self.email_input.text.strip().lower()
        if not email:
            self.error_label.text = "Please enter your email."
            return
        try:
            response = requests.post(
                f"{API_BASE}/sendOtp",
                json={"email": email},
                headers={"Content-Type": "application/json"}
            )
            data = response.json()
            if response.ok:
                self.error_label.text = ""
                self.otp_input.opacity = 1
                self.otp_input.disabled = False
                self.verify_button.opacity = 1
                self.verify_button.disabled = False
                self.send_button.disabled = True
                self.email_input.disabled = True
                self.resend_button.opacity = 1
                self.resend_button.disabled = False
            else:
                self.error_label.text = data.get("message", "An error occurred.")
        except Exception as e:
            self.error_label.text = "Failed to connect to the server."

    def handle_verify_otp(self, instance):
        self.error_label.text = ""
        email = self.email_input.text.strip().lower()
        otp = self.otp_input.text.strip()
        if not otp:
            self.error_label.text = "Please enter the OTP."
            return
        try:
            response = requests.post(
                f"{API_BASE}/verifyOtp",
                json={"email": email, "otp": otp},
                headers={"Content-Type": "application/json"}
            )
            data = response.json()
            if response.ok:
                token = data.get("token")
                if token:
                    with open(TOKEN_FILE, "w") as f:
                        f.write(token)
                    self.manager.current = "main"
                    app = App.get_running_app()
                    app.fetch_slack_id_and_load_main()
                else:
                    self.error_label.text = "No token received."
            else:
                self.error_label.text = data.get("message", "Invalid OTP.")
        except Exception as e:
            self.error_label.text = "Failed to verify OTP."

    def handle_resend_otp(self, instance):
        self.resend_button.disabled = True
        self.handle_send_otp(instance)
        Clock.schedule_once(lambda dt: setattr(self.resend_button, 'disabled', False), 30)  # 30 seconds cooldown

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.slack_id = None
        self.apps_data = {}
        self.offline_manager = OfflineHeartbeatManager()
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Profile picture section
        self.profile_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=80)
        self.profile_picture = Image(size_hint=(None, None), size=(60, 60), pos_hint={'center_x': 0.5, 'center_y': 0.5})
        self.profile_layout.add_widget(self.profile_picture)
        self.layout.add_widget(self.profile_layout)
        
        # Welcome message
        self.welcome_label = Label(text="Welcome!", font_size=24, size_hint_y=None, height=40)
        self.layout.add_widget(self.welcome_label)
        
        saved_api_key = ""
        if os.path.exists(HACKATIME_KEY_FILE):
            with open(HACKATIME_KEY_FILE, "r") as f:
                saved_api_key = f.read().strip()
        self.api_key_input = TextInput(hint_text="Hackatime API Key", multiline=False, text=saved_api_key)
        self.api_key_input.bind(text=self.on_api_key_change)
        self.layout.add_widget(self.api_key_input)
        self.language_input = TextInput(hint_text="Language (e.g. JavaScript)", multiline=False)
        self.layout.add_widget(self.language_input)
        self.app_spinner = Spinner(text="Select an app", values=())
        self.app_spinner.bind(text=self.on_app_selected)
        self.layout.add_widget(self.app_spinner)
        self.project_spinner = Spinner(text="Select a project", values=())
        self.layout.add_widget(self.project_spinner)
        self.unlogged_label = Label(text="Unlogged Time: --:--:-- hours")
        self.layout.add_widget(self.unlogged_label)
        self.timer_label = Label(text="00:00:00", font_size=48)
        self.layout.add_widget(self.timer_label)
        self.start_stop_button = Button(text="Start Logging")
        self.start_stop_button.bind(on_press=self.toggle_logging)
        self.layout.add_widget(self.start_stop_button)
        self.test_heartbeat_button = Button(text="Test Heartbeat")
        self.test_heartbeat_button.bind(on_press=self.test_heartbeat)
        self.layout.add_widget(self.test_heartbeat_button)
        self.heartbeat_status_label = Label(text="", color=(0,1,0,1))
        self.layout.add_widget(self.heartbeat_status_label)
        
        # Offline status label
        self.offline_status_label = Label(text="", color=(1,0.5,0,1), size_hint_y=None, height=30)
        self.layout.add_widget(self.offline_status_label)

        self.view_unsynced_button = Button(text="View Unsynced Heartbeats")
        self.view_unsynced_button.bind(on_press=self.show_unsynced_heartbeats)
        self.layout.add_widget(self.view_unsynced_button)
        
        self.logout_button = Button(text="Logout")
        self.logout_button.bind(on_press=self.logout)
        self.layout.add_widget(self.logout_button)
        self.is_logging = False
        self.seconds = 0
        self.timer_event = None
        self.heartbeat_event = None
        self.sync_event = None
        self.add_widget(self.layout)

    def set_slack_id(self, slack_id, profile_picture_url=None, full_name=None):
        self.slack_id = slack_id
        print(f"Setting slack_id: {slack_id}, full_name: {full_name}")
        if profile_picture_url:
            try:
                # Download the image with requests
                response = requests.get(profile_picture_url, stream=True)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type')
                    ext = mimetypes.guess_extension(content_type) or '.png'
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    for chunk in response.iter_content(1024):
                        temp_file.write(chunk)
                    temp_file.close()
                    self.profile_picture.source = temp_file.name
                    self.profile_temp_file = temp_file.name
                else:
                    print(f"Failed to download profile picture: {response.status_code}")
            except Exception as e:
                print(f"Error loading profile picture: {e}")
        
        # Update welcome message with full name
        if full_name:
            self.welcome_label.text = f"Welcome, {full_name}!"
            print(f"Updated welcome message to: Welcome, {full_name}!")
        else:
            self.welcome_label.text = "Welcome!"
            print("Updated welcome message to: Welcome!")
            
        self.fetch_apps()

    def fetch_apps(self):
        if not self.slack_id:
            self.app_spinner.values = ()
            self.project_spinner.values = ()
            return
        try:
            response = requests.get(
                f"{API_BASE}/getUnloggedTimeForUser?slackId={self.slack_id}",
                headers={"Accept": "application/json"}
            )
            data = response.json()
            print("Using slack_id:", self.slack_id)
            print("API response from getUnloggedTimeForUser:", data)
            self.apps_data = data.get("apps", {})
            app_names = list(self.apps_data.keys())
            if app_names:
                self.app_spinner.values = tuple(app_names)
                self.app_spinner.text = app_names[0]
                self.on_app_selected(self.app_spinner, app_names[0])
            else:
                self.app_spinner.values = ()
                self.unlogged_label.text = "Unlogged Time: --:--:-- hours"
                self.project_spinner.values = ()
        except Exception as e:
            print("Error fetching apps:", e)
            self.app_spinner.values = ()
            self.unlogged_label.text = "Unlogged Time: --:--:-- hours"
            self.project_spinner.values = ()

    def on_app_selected(self, spinner, app_name):
        app_info = self.apps_data.get(app_name, {})
        unlogged = app_info.get("unloggedHours", 0)
        self.unlogged_label.text = f"Unlogged Time: {unlogged} hours"
        # Fetch projects for this app from the API
        if self.slack_id and app_name:
            try:
                response = requests.get(
                    f"{API_BASE}/getAppUserHackatimeProjects?slackId={self.slack_id}&appName={app_name}",
                    headers={"Accept": "application/json"}
                )
                data = response.json()
                print(f"Projects API response for app '{app_name}':", data)
                projects = data.get("projects", [])
                project_names = [p["name"] if isinstance(p, dict) and "name" in p else str(p) for p in projects]
                if project_names:
                    self.project_spinner.values = tuple(project_names)
                    self.project_spinner.text = project_names[0]
                else:
                    self.project_spinner.values = ()
                    self.project_spinner.text = "Select a project"
            except Exception as e:
                print(f"Error fetching projects for app '{app_name}':", e)
                self.project_spinner.values = ()
                self.project_spinner.text = "Select a project"
        else:
            self.project_spinner.values = ()
            self.project_spinner.text = "Select a project"

    def toggle_logging(self, instance):
        if not self.is_logging:
            self.start_logging()
        else:
            self.stop_logging()

    def start_logging(self):
        self.is_logging = True
        self.start_stop_button.text = "Stop Logging"
        self.seconds = 0
        self.timer_label.text = "00:00:00"
        self.timer_event = Clock.schedule_interval(self.update_timer, 1)
        self.heartbeat_event = Clock.schedule_interval(self.send_heartbeat, 60)
        # self.sync_event = Clock.schedule_interval(self.sync_offline_heartbeats, 30)

    def stop_logging(self):
        self.is_logging = False
        self.start_stop_button.text = "Start Logging"
        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None
        if hasattr(self, 'heartbeat_event') and self.heartbeat_event:
            self.heartbeat_event.cancel()
            self.heartbeat_event = None
        if hasattr(self, 'sync_event') and self.sync_event:
            self.sync_event.cancel()
            self.sync_event = None

    def update_timer(self, dt):
        self.seconds += 1
        hours = self.seconds // 3600
        minutes = (self.seconds % 3600) // 60
        secs = self.seconds % 60
        self.timer_label.text = f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def test_heartbeat(self, instance):
        project = self.project_spinner.text
        api_key = self.api_key_input.text.strip()
        language = self.language_input.text.strip() or 'JavaScript'
        if not project or project == 'Select a project':
            self.heartbeat_status_label.text = "No project selected."
            self.heartbeat_status_label.color = (1,0,0,1)
            print("No project selected.")
            return
        if not api_key:
            self.heartbeat_status_label.text = "No API key entered."
            self.heartbeat_status_label.color = (1,0,0,1)
            print("No API key entered.")
            return
        payload = {
            "entity": project,
            "type": "file",
            "time": int(__import__('time').time()),
            "project": project,
            "language": language,
            "hackatimeToken": api_key,
            "is_write": True
        }
        try:
            response = requests.post(
                f"{API_BASE}/heartbeats",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            print("Heartbeat response:", response.status_code, response.text)
            if response.status_code in (200, 202):
                self.heartbeat_status_label.text = "Heartbeat OK!"
                self.heartbeat_status_label.color = (0,1,0,1)
            else:
                self.heartbeat_status_label.text = f"Heartbeat failed: {response.status_code}"
                self.heartbeat_status_label.color = (1,0,0,1)
        except Exception as e:
            self.heartbeat_status_label.text = "Error sending heartbeat."
            self.heartbeat_status_label.color = (1,0,0,1)
            print("Error sending heartbeat:", e)

    def send_heartbeat(self, dt):
        project = self.project_spinner.text
        api_key = self.api_key_input.text.strip()
        language = self.language_input.text.strip() or 'JavaScript'
        if not self.is_logging:
            return
        if not project or project == 'Select a project':
            print("No project selected for heartbeat.")
            return
        if not api_key:
            print("No API key entered for heartbeat.")
            return
        payload = {
            "entity": project,
            "type": "file",
            "time": int(__import__('time').time()),
            "project": project,
            "language": language,
            "hackatimeToken": api_key,
            "is_write": True
        }
        try:
            response = requests.post(
                f"{API_BASE}/heartbeats",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            print(f"[TIMER] Heartbeat response: {response.status_code} {response.text}")
            
            if response.status_code in (200, 202):
                self.offline_status_label.text = ""
            else:
                # Save to offline storage if API call fails
                self.offline_manager.save_heartbeat_offline(payload)
                self.offline_status_label.text = f"Offline: {response.status_code}"
                
        except Exception as e:
            print("[TIMER] Error sending heartbeat:", e)
            # Save to offline storage if network error
            self.offline_manager.save_heartbeat_offline(payload)
            self.offline_status_label.text = "Offline: Network Error"

    def logout(self, instance):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        # Clean up temporary profile picture file
        if hasattr(self, 'profile_temp_file') and os.path.exists(self.profile_temp_file):
            try:
                os.remove(self.profile_temp_file)
            except:
                pass
        self.manager.current = "login"

    def on_api_key_change(self, instance, value):
        with open(HACKATIME_KEY_FILE, "w") as f:
            f.write(value.strip())

    def show_unsynced_heartbeats(self, instance):
        heartbeats = self.offline_manager.get_offline_heartbeats()
        content = BoxLayout(orientation='vertical', spacing=5)
        scroll = ScrollView(size_hint=(1, 0.8))
        inner = BoxLayout(orientation='vertical', size_hint_y=None)
        inner.bind(minimum_height=inner.setter('height'))
        if not heartbeats:
            inner.add_widget(Label(text="No unsynced heartbeats!", size_hint_y=None, height=30))
        else:
            for key, hb in heartbeats:
                desc = f"{hb.get('project', 'unknown')} @ {datetime.fromtimestamp(hb.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S')}"
                row = BoxLayout(orientation='horizontal', size_hint_y=None, height=30)
                row.add_widget(Label(text=desc))
                del_btn = Button(text="Delete", size_hint_x=None, width=80)
                del_btn.bind(on_press=lambda btn, k=key: self.delete_unsynced_heartbeat(k))
                row.add_widget(del_btn)
                inner.add_widget(row)
        scroll.add_widget(inner)
        content.add_widget(scroll)
        if heartbeats:
            del_all_btn = Button(text="Delete All Unsynced Heartbeats", size_hint_y=None, height=40)
            del_all_btn.bind(on_press=lambda btn: self.delete_all_unsynced_heartbeats())
            content.add_widget(del_all_btn)
        close_btn = Button(text="Close", size_hint_y=None, height=40)
        content.add_widget(close_btn)
        popup = Popup(title="Unsynced Heartbeats", content=content, size_hint=(0.9, 0.7))
        close_btn.bind(on_press=popup.dismiss)
        self._unsynced_popup = popup
        popup.open()

    def delete_unsynced_heartbeat(self, key):
        self.offline_manager.remove_heartbeat(key)
        if hasattr(self, '_unsynced_popup'):
            self._unsynced_popup.dismiss()
        self.show_unsynced_heartbeats(None)

    def delete_all_unsynced_heartbeats(self):
        heartbeats = self.offline_manager.get_offline_heartbeats()
        for key, _ in heartbeats:
            self.offline_manager.remove_heartbeat(key)
        if hasattr(self, '_unsynced_popup'):
            self._unsynced_popup.dismiss()
        self.show_unsynced_heartbeats(None)

class TimeLoggerApp(App):
    def build(self):
        self.sm = ScreenManager()
        self.login_screen = LoginScreen(name="login")
        self.main_screen = MainScreen(name="main")
        self.sm.add_widget(self.login_screen)
        self.sm.add_widget(self.main_screen)
        # Auto-login if token exists
        if os.path.exists(TOKEN_FILE):
            self.sm.current = "main"
            self.fetch_slack_id_and_load_main()
        else:
            self.sm.current = "login"
        return self.sm

    def fetch_slack_id_and_load_main(self):
        # Read token
        try:
            with open(TOKEN_FILE, "r") as f:
                token = f.read().strip()
            response = requests.get(
                f"{API_BASE}/getMyPfp?token={token}",
                headers={"Accept": "application/json"}
            )
            data = response.json()
            slack_id = data.get("slackId")
            if isinstance(slack_id, list):
                slack_id = slack_id[0] if slack_id else None
            
            # Extract profile picture URL
            profile_picture_url = None
            pfp_data = data.get("pfp", [])
            if pfp_data and len(pfp_data) > 0:
                profile_picture_url = pfp_data[0].get("url")
            
            if slack_id:
                # Fetch neighbor details to get full name
                self.fetch_neighbor_details(slack_id, profile_picture_url)
        except Exception as e:
            pass

    def fetch_neighbor_details(self, slack_id, profile_picture_url):
        try:
            print(f"Fetching neighbor details for slack_id: {slack_id}")
            response = requests.get(
                f"{API_BASE}/getNeighborDetails?slackId={slack_id}",
                headers={"Accept": "application/json"}
            )
            print(f"Neighbor details response status: {response.status_code}")
            data = response.json()
            print(f"Neighbor details response data: {data}")
            
            # Extract full_name and pfp from the nested neighbor object
            neighbor_data = data.get("neighbor", {})
            full_name = neighbor_data.get("fullName")
            profile_picture_url = neighbor_data.get("pfp")  # Get pfp from neighbor
            print(f"Extracted full_name: {full_name}, pfp: {profile_picture_url}")
            
            self.main_screen.set_slack_id(slack_id, profile_picture_url, full_name)
        except Exception as e:
            print(f"Error fetching neighbor details: {e}")
            # Fallback to setting without full name or pfp
            self.main_screen.set_slack_id(slack_id, profile_picture_url)

if __name__ == "__main__":
    TimeLoggerApp().run()