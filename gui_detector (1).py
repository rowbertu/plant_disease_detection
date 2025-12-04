import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkinter.filedialog import askopenfilename
import cv2
from PIL import Image, ImageTk
import time
import numpy as np
import traceback

# Import the analysis functions
try:
    import analysis_logic as al
    print("✓ analysis_logic module imported successfully")
except ImportError as e:
    print(f"ERROR: Could not import analysis_logic: {e}")
    print("Make sure analysis_logic.py is in the same directory!")
    exit(1)

# --- Tkinter Colors and Styles ---
BG_COLOR = "#f0fdf4" 	# Light green background
PRIMARY_COLOR = "#10b981" 	# Green-500
DARK_COLOR = "#047857" 	# Green-700
BORDER_COLOR = "#d1d5db" 	# Gray border
RED_COLOR = "#ef4444" 	# Red-500
YELLOW_COLOR = "#f59e0b" 	# Yellow-600
SCAN_COLOR = "#3b82f6" 	# Blue-500
WAITING_COLOR = "#6b7280" 	# Gray-500

class PlantDetectorApp:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.configure(bg=BG_COLOR)
        
        self.window.geometry("1500x850")
        
        # --- State Variables ---
        self.vid = None
        self.camera_available = False
        self.initialize_camera()
        
        self.current_bbox = None
        self.is_scanning = False
        self.last_analysis_result = None
        self.frame_count = 0
        self.analysis_interval = 30 # No longer used for auto-scan, but kept
        
        self.selected_plant_var = tk.StringVar(self.window)
        
        # NEW STATE VARIABLES FOR CONTROL BUTTONS
        self.is_live = True 	# True: Video runs live; False: Video is paused on a frame
        self.paused_frame = None 	# Stores the frame when analysis is triggered
        
        # --- UI Setup ---
        self.setup_ui()
        
        if al.PLANT_TYPES:
            self.selected_plant_var.set(al.PLANT_TYPES[0])
            
        # --- Start Video Loop ---
        self.delay = 15
        self.update_video()
        
        # --- Handle closing ---
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def initialize_camera(self):
        """Initialize camera"""
        try:
            self.vid = cv2.VideoCapture(0)
            
            if self.vid.isOpened():
                self.camera_available = True
                self.vid.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.vid.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                
                self.vid_width = int(self.vid.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.vid_height = int(self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"✓ Camera opened: {self.vid_width}x{self.vid_height}")
            else:
                self.camera_available = False
                self.vid_width = 640
                self.vid_height = 480
                print("⚠ Camera not available")
        except Exception as e:
            print(f"⚠ Camera error: {e}")
            self.camera_available = False
            self.vid_width = 640
            self.vid_height = 480

    def setup_ui(self):
        """Setup the complete user interface"""
        
        main_container = tk.Frame(self.window, bg=BG_COLOR)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        left_column = tk.Frame(main_container, bg=BG_COLOR)
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        right_column = tk.Frame(main_container, bg=BG_COLOR, width=500)
        right_column.pack(side="right", fill="both", padx=(10, 0))
        right_column.pack_propagate(False)
        
        self.create_video_panel(left_column)
        self.create_results_panel(right_column)

    def create_video_panel(self, parent):
        """Create the video feed panel with controls"""
        
        video_card = tk.Frame(parent, bg='white', relief='solid', bd=2, highlightbackground=BORDER_COLOR)
        video_card.pack(fill="both", expand=True)
        
        control_frame = tk.Frame(video_card, bg='white')
        control_frame.pack(fill='x', padx=15, pady=(15, 10))
        
        tk.Label(control_frame, 
                 text="Live Camera Feed", 
                 font=('Arial', 16, 'bold'), 
                 fg=DARK_COLOR, 
                 bg='white').pack(side='left', anchor='w')
        
        # --- NEW: Control Buttons ---
        self.scan_button = tk.Button(control_frame, text="Scan/Hold 📸", command=self.toggle_scan, 
                                     bg=PRIMARY_COLOR, fg='white', font=('Arial', 10, 'bold'), relief=tk.FLAT)
        self.scan_button.pack(side='right', padx=10)

        self.quit_button = tk.Button(control_frame, text="Quit App 🛑", command=self.quit_app, 
                                     bg=RED_COLOR, fg='white', font=('Arial', 10, 'bold'), relief=tk.FLAT)
        self.quit_button.pack(side='right', padx=10)
        
        tk.Label(control_frame, 
                 text="Plant Species:", 
                 font=('Arial', 11, 'bold'), 
                 fg=DARK_COLOR, 
                 bg='white').pack(side='right', padx=(10, 5))
                 
        if al.PLANT_TYPES:
            self.plant_selector = ttk.Combobox(control_frame, 
                                               textvariable=self.selected_plant_var, 
                                               values=al.PLANT_TYPES, 
                                               state="readonly",
                                               width=15)
            self.plant_selector.pack(side='right')
        else:
            tk.Label(control_frame, text="No Plant Types Found", fg=RED_COLOR, bg='white').pack(side='right')

        canvas_frame = tk.Frame(video_card, bg='black')
        canvas_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.canvas = tk.Canvas(canvas_frame, 
                                 bg='black',
                                 highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    # --- NEW: Control Logic ---

    def toggle_scan(self):
        """Toggles between live video and paused analysis frame."""
        if not self.camera_available:
            messagebox.showinfo("Error", "Camera not available for scanning.")
            return

        if self.is_live:
            # 1. Capture the current frame and pause the video display
            self.is_live = False
            self.scan_button.config(text="Resume Live Feed ▶️", bg=YELLOW_COLOR)
            print("Manual Scan Triggered. Video Paused on Frame.")
            
            # 2. Run analysis immediately on the paused_frame
            if self.paused_frame is not None:
                selected_plant = self.selected_plant_var.get()
                if selected_plant and selected_plant != "N/A":
                    self.run_analysis(self.paused_frame.copy(), selected_plant)
        else:
            # Resume live video
            self.is_live = True
            self.paused_frame = None
            self.scan_button.config(text="Scan/Hold 📸", bg=PRIMARY_COLOR)
            self.last_analysis_result = None # Clear analysis result when resuming live
            self.show_waiting_state()
            print("Resuming Live Feed.")

    def quit_app(self):
        """Handles graceful application shutdown when Quit button is pressed."""
        self.on_closing()

    # --- End NEW: Control Logic ---

    def create_results_panel(self, parent):
        """Create the results panel"""
        
        title_frame = tk.Frame(parent, bg=PRIMARY_COLOR, height=60)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame,
                 text="CNN Classification Results",
                 font=('Arial', 16, 'bold'),
                 fg='white',
                 bg=PRIMARY_COLOR).pack(pady=15)
        
        results_container = tk.Frame(parent, bg='white')
        results_container.pack(fill='both', expand=True)
        
        canvas = tk.Canvas(results_container, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(results_container, orient="vertical", command=canvas.yview)
        
        self.results_frame = tk.Frame(canvas, bg='white')
        
        self.results_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.results_frame, anchor="nw", width=480)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.build_results_content()

    def build_results_content(self):
        """Build the results panel content"""
        
        # === HEALTH STATUS BOX ===
        self.status_frame = tk.Frame(self.results_frame, bg=WAITING_COLOR, height=60)
        self.status_frame.pack(fill='x', padx=15, pady=(15, 10))
        self.status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(self.status_frame,
                                     text="HEALTH STATUS: WAITING FOR PLANT", 
                                     font=('Arial', 14, 'bold'),
                                     fg='white',
                                     bg=WAITING_COLOR)
        self.status_label.pack(expand=True)
        
        # === DISEASE INFO BOX ===
        info_box = tk.Frame(self.results_frame, bg='white', relief='solid', bd=1)
        info_box.pack(fill='x', padx=15, pady=10)
        
        # Plant Type (Reference)
        plant_row = tk.Frame(info_box, bg='white')
        plant_row.pack(fill='x', padx=15, pady=8)
        
        tk.Label(plant_row,
                 text="Plant Type:",
                 font=('Arial', 11),
                 bg='white',
                 fg='black').pack(side='left')
        
        self.plant_label = tk.Label(plant_row,
                                     text="N/A", 
                                     font=('Arial', 11, 'bold'),
                                     bg='white',
                                     fg=PRIMARY_COLOR)
        self.plant_label.pack(side='right')
        
        tk.Frame(info_box, bg=BORDER_COLOR, height=1).pack(fill='x', padx=15)
        
        # Disease Detected
        disease_row = tk.Frame(info_box, bg='white')
        disease_row.pack(fill='x', padx=15, pady=8)
        
        tk.Label(disease_row,
                 text="Disease Detected:",
                 font=('Arial', 11),
                 bg='white',
                 fg='black').pack(side='left')
        
        self.disease_label = tk.Label(disease_row,
                                     text="N/A",
                                     font=('Arial', 11, 'bold'),
                                     bg='white',
                                     fg=PRIMARY_COLOR)
        self.disease_label.pack(side='right')
        
        tk.Frame(info_box, bg=BORDER_COLOR, height=1).pack(fill='x', padx=15)
        
        # Disease Type
        type_row = tk.Frame(info_box, bg='white')
        type_row.pack(fill='x', padx=15, pady=8)
        
        tk.Label(type_row,
                 text="Type:",
                 font=('Arial', 11),
                 bg='white',
                 fg='black').pack(side='left')
        
        self.type_label = tk.Label(type_row,
                                 text="N/A",
                                 font=('Arial', 11, 'bold'),
                                 bg='white',
                                 fg='#f59e0b')
        self.type_label.pack(side='right')
        
        tk.Frame(info_box, bg=BORDER_COLOR, height=1).pack(fill='x', padx=15)
        
        # Confidence
        confidence_row = tk.Frame(info_box, bg='white')
        confidence_row.pack(fill='x', padx=15, pady=8)
        
        tk.Label(confidence_row,
                 text="Confidence:",
                 font=('Arial', 11),
                 bg='white',
                 fg='black').pack(side='left')
        
        self.confidence_label = tk.Label(confidence_row,
                                         text="0.00%",
                                         font=('Arial', 11, 'bold'),
                                         bg='white',
                                         fg='black')
        self.confidence_label.pack(side='right')
        
        # === SEVERITY LEVEL ===
        severity_box = tk.Frame(self.results_frame, bg='white', relief='solid', bd=1)
        severity_box.pack(fill='x', padx=15, pady=10)
        
        tk.Label(severity_box,
                 text="Severity Level (Simulated)",
                 font=('Arial', 11, 'bold'),
                 bg='white',
                 fg='black').pack(anchor='w', padx=15, pady=(10, 5))
        
        self.severity_bar = ttk.Progressbar(severity_box,
                                             orient='horizontal',
                                             mode='determinate',
                                             length=400)
        self.severity_bar.pack(fill='x', padx=15, pady=(0, 10))
        
        # === CAUSE/EXPLANATION ===
        self.create_info_section("Cause & Explanation", "cause", "#9333ea", "#f3e8ff")
        self.create_info_section("Discoloration Pattern", "discoloration", PRIMARY_COLOR, "#e0f2fe")
        self.create_info_section("Symptoms Detected", "symptoms", RED_COLOR, "#fee2e2")
        self.create_info_section("Treatment Recommendations", "recommendations", PRIMARY_COLOR, "#dcfce7")
        self.create_info_section("Preventive Measures", "preventive", YELLOW_COLOR, "#fef3c7")
        
        self.show_waiting_state()

    def create_info_section(self, title, var_name, title_color, bg_color):
        """Create an information section with title and text area"""
        section_frame = tk.Frame(self.results_frame, bg='white', relief='solid', bd=1)
        section_frame.pack(fill='x', padx=15, pady=10)
        
        title_label = tk.Label(section_frame,
                               text=title,
                               font=('Arial', 11, 'bold'),
                               bg=bg_color,
                               fg=title_color)
        title_label.pack(fill='x', padx=0, pady=0)
        
        text_widget = tk.Text(section_frame,
                               height=4,
                               bg='white',
                               fg='black',
                               font=('Arial', 10),
                               wrap='word',
                               relief='flat',
                               padx=10,
                               pady=5)
        text_widget.pack(fill='x', padx=0, pady=0)
        text_widget.config(state='disabled')
        
        setattr(self, f"{var_name}_text", text_widget)

    def show_waiting_state(self):
        """Show waiting state when no plant is detected"""
        self.status_frame.config(bg=WAITING_COLOR)
        self.status_label.config(text="HEALTH STATUS: WAITING FOR PLANT", 
                                 bg=WAITING_COLOR)
        
        self.plant_label.config(text="N/A")
        self.disease_label.config(text="N/A")
        self.type_label.config(text="N/A")
        self.confidence_label.config(text="0.00%")
        self.severity_bar['value'] = 0
        
        self.update_text_widget(self.cause_text, ["• Waiting for plant detection..."])
        self.update_text_widget(self.discoloration_text, ["• Waiting for plant detection..."])
        self.update_text_widget(self.symptoms_text, ["• Waiting for plant detection..."])
        self.update_text_widget(self.recommendations_text, ["• Waiting for plant detection..."])
        self.update_text_widget(self.preventive_text, ["• Waiting for plant detection..."])

    def update_text_widget(self, text_widget, items):
        """Update a text widget with list of items"""
        text_widget.config(state='normal')
        text_widget.delete('1.0', tk.END)
        
        if items:
            for item in items:
                text_widget.insert(tk.END, f"{item}\n")
        else:
            text_widget.insert(tk.END, "• No data available\n")
        
        text_widget.config(state='disabled')

    def get_dummy_frame(self):
        """Generate placeholder frame when camera unavailable"""
        frame = np.zeros((self.vid_height, self.vid_width, 3), dtype=np.uint8)
        frame[:] = (40, 40, 40)
        
        cv2.rectangle(frame, (50, 50), (self.vid_width - 50, self.vid_height - 50), 
                      (100, 100, 100), 3)
        
        text_lines = [
            "CAMERA UNAVAILABLE", "", "Please check:", "• Camera is connected", 
            "• No other app is using it", "• Camera permissions enabled"
        ]
        
        y_offset = int(self.vid_height / 2) - 60
        for line in text_lines:
            if line:
                cv2.putText(frame, line, (70, y_offset), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1, cv2.LINE_AA)
            y_offset += 30
        
        return frame

    def update_video(self):
        """Main video update loop"""
        # --- Frame reading depends on self.is_live state ---
        if self.is_live:
            if self.camera_available and self.vid and self.vid.isOpened():
                ret, frame = self.vid.read()
                # Store the last live frame for manual analysis
                if ret:
                    self.paused_frame = frame.copy()
            else:
                ret = True
                frame = self.get_dummy_frame()
                self.paused_frame = None # Cannot analyze dummy frame
        else:
            # If not live, display the stored paused frame
            if self.paused_frame is not None:
                ret = True
                frame = self.paused_frame
            else:
                ret = True
                frame = self.get_dummy_frame() # Fallback

        if ret:
            # === AUTOMATIC SCANNING LOGIC REMOVED HERE ===
            
            # Drawing overlays (Runs on both live and paused frame)
            if self.camera_available:
                if self.is_scanning:
                    self.draw_scanning_overlay(frame)
                
                if self.current_bbox and self.last_analysis_result:
                    self.draw_bounding_box(frame, self.current_bbox, 
                                             self.last_analysis_result['status'],
                                             self.last_analysis_result['disease'])

            self.display_frame(frame)
            
        self.window.after(self.delay, self.update_video)

    def display_frame(self, frame):
        """Display the frame on canvas"""
        try:
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            img = Image.fromarray(cv2image)
            
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()

            if canvas_w > 1 and canvas_h > 1:
                ratio = min(canvas_w / self.vid_width, canvas_h / self.vid_height)
                new_w = int(self.vid_width * ratio)
                new_h = int(self.vid_height * ratio)
                
                if new_w > 0 and new_h > 0:
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    
                    self.photo = ImageTk.PhotoImage(image=img)
                    self.canvas.delete("all")
                    self.canvas.create_image(canvas_w / 2, canvas_h / 2, 
                                             image=self.photo, anchor=tk.CENTER)
        except Exception as e:
            pass

    def draw_bounding_box(self, frame, bbox_normalized, status, disease_name):
        """Draw bounding box on frame"""
        H, W, _ = frame.shape
        
        x1 = int(bbox_normalized[0] * W / 1000)
        y1 = int(bbox_normalized[1] * H / 1000)
        x2 = int(bbox_normalized[2] * W / 1000)
        y2 = int(bbox_normalized[3] * H / 1000)

        color_map = {
            "Healthy": (0, 255, 0), "Diseased": (0, 0, 255), "Stressed": (0, 255, 255)
        }
        color = color_map.get(status, (255, 255, 255))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        
        label = f"{status.upper()} - {disease_name}"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 20), 
                      (x1 + label_size[0] + 10, y1), color, -1)
        
        cv2.putText(frame, label, (x1 + 5, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    def draw_scanning_overlay(self, frame):
        """Draw scanning indicator"""
        H, W, _ = frame.shape
        
        text = "SCANNING..."
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0]
        text_x = int((W - text_size[0]) / 2)
        text_y = int((H + text_size[1]) / 2)
        
        pulse = int((np.sin(time.time() * 10) + 1) * 127.5)
        color = (255, pulse, 0)
        
        overlay = frame.copy()
        cv2.rectangle(overlay, 
                      (text_x - 20, text_y - text_size[1] - 10), 
                      (text_x + text_size[0] + 20, text_y + 10), 
                      (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
        
        cv2.putText(frame, text, (text_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3, cv2.LINE_AA)

    def run_analysis(self, frame, plant_type):
        """Run CNN analysis on frame, passing the selected plant type"""
        self.is_scanning = True
        self.update_results_panel_scanning()
        self.window.update_idletasks()
        
        try:
            result = al.analyze_frame_with_tf(frame, plant_type) 
            
            if result:
                self.last_analysis_result = result
                self.current_bbox = result.get('bbox', [250, 200, 750, 700]) 
                self.update_results_panel(result)
            else:
                self.last_analysis_result = None
                # Set a fallback bbox for visual debugging if analysis returns None
                fallback_info = al.DISEASE_DATABASE.get(f"{plant_type} healthy") or {"bbox": [250, 200, 750, 700]}
                self.current_bbox = fallback_info["bbox"]
                
                # Only show waiting state if still in live mode OR if manually paused and analysis failed
                if self.is_live or not self.last_analysis_result:
                    self.show_waiting_state()
                
        except Exception as e:
            print(f"Analysis error: {e}")
            traceback.print_exc()
        finally:
            self.is_scanning = False

    def update_results_panel_scanning(self):
        """Update UI to show scanning state"""
        self.status_frame.config(bg=SCAN_COLOR)
        self.status_label.config(text="SCANNING...", bg=SCAN_COLOR)

    def update_results_panel(self, result):
        """Update the results display with analysis results"""
        status = result["status"]
        
        if status == "Healthy": bg, status_text = PRIMARY_COLOR, f"HEALTH STATUS: {status.upper()} 🥬"
        elif status == "Diseased": bg, status_text = RED_COLOR, f"HEALTH STATUS: {status.upper()} 🥀"
        elif status == "Stressed": bg, status_text = YELLOW_COLOR, f"HEALTH STATUS: {status.upper()} ⚠️"
        else: bg, status_text = WAITING_COLOR, "HEALTH STATUS: UNKNOWN"
        
        self.status_frame.config(bg=bg)
        self.status_label.config(text=status_text, bg=bg)
        
        self.plant_label.config(text=result.get("plant", "N/A"))
        self.disease_label.config(text=result["disease"])
        self.type_label.config(text=result.get("type", "N/A"))
        self.confidence_label.config(text=result["confidence"])
        
        severity_map = {"none": 0, "mild": 33, "moderate": 66, "severe": 100}
        self.severity_bar['value'] = severity_map.get(result["severity"].lower(), 0)
        
        self.update_text_widget(self.cause_text, [result.get("cause", "• No information available")])
        self.update_text_widget(self.discoloration_text, [f"• {item}" for item in result.get("discoloration", [])])
        self.update_text_widget(self.symptoms_text, [f"• {item}" for item in result.get("symptoms", [])])
        self.update_text_widget(self.recommendations_text, [f"• {item}" for item in result.get("recommendations", [])])
        self.update_text_widget(self.preventive_text, [f"• {item}" for item in result.get("preventive", [])])

    def on_closing(self):
        """Clean up on close (called by window close and Quit button)"""
        if self.vid and self.vid.isOpened():
            self.vid.release()
        self.window.destroy()

# --- Main Program ---
if __name__ == "__main__":
    print("\n" + "="*70)
    print("PLANT DISEASE DETECTOR - CNN GUI")
    print("="*70)
    print("\n✓ Starting application...")
    
    try:
        root = tk.Tk()
        app = PlantDetectorApp(root, "🌿 Plant Disease Detector (CNN)")
        root.mainloop()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
    
    print("\n✓ Application closed")
    print("="*70)