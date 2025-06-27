import requests
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
import os

API_BASE = "https://adventure-time.hackclub.dev/api"
TOKEN_FILE = "auth_token.txt"
HACKATIME_KEY_FILE = "hackatime_api_key.txt"

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

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.slack_id = None
        self.apps_data = {}
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
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
        self.logout_button = Button(text="Logout")
        self.logout_button.bind(on_press=self.logout)
        self.layout.add_widget(self.logout_button)
        self.is_logging = False
        self.seconds = 0
        self.timer_event = None
        self.heartbeat_event = None
        self.add_widget(self.layout)

    def set_slack_id(self, slack_id):
        self.slack_id = slack_id
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
        self.heartbeat_event = Clock.schedule_interval(self.send_heartbeat, 5)

    def stop_logging(self):
        self.is_logging = False
        self.start_stop_button.text = "Start Logging"
        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None
        if hasattr(self, 'heartbeat_event') and self.heartbeat_event:
            self.heartbeat_event.cancel()
            self.heartbeat_event = None

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
                headers={"Content-Type": "application/json"}
            )
            print(f"[TIMER] Heartbeat response: {response.status_code} {response.text}")
        except Exception as e:
            print("[TIMER] Error sending heartbeat:", e)

    def logout(self, instance):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self.manager.current = "login"

    def on_api_key_change(self, instance, value):
        with open(HACKATIME_KEY_FILE, "w") as f:
            f.write(value.strip())

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
            if slack_id:
                self.main_screen.set_slack_id(slack_id)
        except Exception as e:
            pass

if __name__ == "__main__":
    TimeLoggerApp().run()