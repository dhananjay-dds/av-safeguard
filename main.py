import os
import math
import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal

# --- PDF LIBRARIES ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Frame, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String

# --- IMPORT V3.1 ENGINE ---
from v3_1_physics_engine import CenterChannelAnalyzer, EarHeightValidator, MaterialPresets

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 1. DATA MODELS (CONSULTANT GRADE)
# ==========================================
class RoomData(BaseModel):
    # --- METADATA ---
    client_name: str = "Client"
    project_name: str = "Home Cinema"
    integrator_name: str = "Integrator"
    
    # --- DIMENSIONS ---
    measurement_unit: Literal["Meters", "Feet"] = "Feet"
    length: float
    width: float
    height: float
    wall_material: str = "drywall_shell"
    
    # --- SCREEN & OPTICAL ---
    screen_width: float
    screen_bottom: float = 3.5
    aspect_ratio: float = 1.777
    screen_gain: float = 1.0
    projector_lumens: int = 2000
    throw_ratio_min: float = 1.4
    throw_ratio_max: float = 2.0
    
    # --- AUDIO & SEATING ---
    seat_dist: float
    ear_height: float = 42.0
    speaker_height: float = 32.0
    speaker_offset: float = 0.0

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def check_hvac_noise(room_vol_ft3):
    if room_vol_ft3 > 5000:
        return "CRITICAL: Large volume. Dedicated NC-30 High-Static unit required."
    elif room_vol_ft3 > 2000:
        return "WARNING: Standard HVAC (NC-45) likely too loud. Specify In-Line Silencers."
    else:
        return "PASS: Standard HVAC acceptable."

def calculate_room_modes(L, W, H):
    modes = {"L": [], "W": [], "H": []}
    for dim, label in [(L, "L"), (W, "W"), (H, "H")]:
        for n in range(1, 3): 
            freq = 1125 / (2 * dim) * n
            modes[label].append(round(freq, 1))
    return modes

# --- UPDATED DIAGRAM FUNCTION (COMPACT VERSION) ---
def draw_room_diagram(room_len_ft, screen_width_ft, seat_dist_ft, req_throw_min):
    # Reduced height from 200 to 130 to fit on one page
    d = Drawing(400, 130) 
    scale = 350 / max(room_len_ft, 20) 
    room_w = room_len_ft * scale
    room_h = 10 * scale 
    # Center the room vertically in the 130px space
    y_start = 65 - (room_h / 2)
    
    # Room Shell
    d.add(Rect(0, y_start, room_w, room_h, fillColor=colors.whitesmoke, strokeColor=colors.black))
    d.add(String(10, y_start - 10, f"DEPTH: {room_len_ft:.1f}'", fontSize=8))

    # Screen
    screen_h_draw = (screen_width_ft / 1.77) * scale 
    d.add(Line(5, 65 - (screen_h_draw/2), 5, 65 + (screen_h_draw/2), strokeWidth=4, strokeColor=colors.blue))
    
    # Seat
    seat_x = seat_dist_ft * scale
    d.add(Circle(seat_x, 65, 5, fillColor=colors.orange, strokeColor=colors.black))
    d.add(String(seat_x - 10, 50, f"SEAT", fontSize=8))

    # Throw Line
    req_x = req_throw_min * scale
    d.add(Line(req_x, 65, 5, 65, strokeColor=colors.green, strokeDashArray=[2,2]))
    
    return d

# --- FOOTER FUNCTION (THE LIABILITY SHIELD) ---
def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 6)
    canvas.setFillColor(colors.grey)
    
    # Disclaimer Text (Perplexity Output)
    disclaimer_lines = [
        "ENGINEERING DISCLAIMER: This Design Validation Report presents theoretical calculations based on provided dimensions.",
        "Real-world acoustic performance depends on construction quality, materials, and installation precision.",
        "The Consultant assumes no liability for construction errors or defects. On-site verification is REQUIRED.",
        "Valid only for design feasibility assessment. Not a guarantee of performance."
    ]
    
    # Draw Footer at bottom of page
    y_pos = 40
    for line in disclaimer_lines:
        canvas.drawCentredString(letter[0]/2.0, y_pos, line)
        y_pos -= 8
        
    canvas.restoreState()

# ==========================================
# 3. MASTER API ENDPOINT
# ==========================================
@app.post("/report")
async def generate_report(room: RoomData):
    # ... [Keep your existing Unit Normalization & Calculation code same as before] ...
    # ... (Copy section A and B from your previous code) ...
    # RE-PASTING THE CALCULATIONS FOR SAFETY SO YOU DON'T BREAK IT:
    if room.measurement_unit == "Meters":
        to_ft = 3.28084
        L_ft, W_ft, H_ft = room.length * to_ft, room.width * to_ft, room.height * to_ft
        ScreenW_ft = room.screen_width * to_ft
        ScreenBot_ft = room.screen_bottom * to_ft
        SeatDist_ft = room.seat_dist * to_ft
        Ear_in = room.ear_height * 0.3937
        Tweet_in = room.speaker_height * 0.3937
        Offset_in = room.speaker_offset * 0.3937
    else:
        L_ft, W_ft, H_ft = room.length, room.width, room.height
        ScreenW_ft = room.screen_width
        ScreenBot_ft = room.screen_bottom
        SeatDist_ft = room.seat_dist
        Ear_in, Tweet_in = room.ear_height, room.speaker_height
        Offset_in = room.speaker_offset

    # Calculations
    ScreenH_ft = ScreenW_ft / room.aspect_ratio
    Area_sq_ft = ScreenW_ft * ScreenH_ft
    FTL = (room.projector_lumens * room.screen_gain) / Area_sq_ft
    Req_Throw = ScreenW_ft * room.throw_ratio_min
    Throw_Pass = "PASS" if (L_ft - 1.5) >= Req_Throw else "FAIL"
    ScreenCenter_ft = ScreenBot_ft + (ScreenH_ft / 2)
    Eye_ft = Ear_in / 12.0
    Vert_View_Angle = math.degrees(math.atan((ScreenCenter_ft - Eye_ft) / SeatDist_ft))
    Vert_View_Pass = "PASS" if Vert_View_Angle <= 15 else "WARN (>15\u00b0)"
    Offset_ft = Offset_in / 12.0
    Horiz_Angle = math.degrees(math.atan(Offset_ft / SeatDist_ft))
    Horiz_Pass = "OPTIMAL" if Horiz_Angle <= 10 else ("ACCEPTABLE" if Horiz_Angle <= 30 else "FAIL")
    speaker_tool = CenterChannelAnalyzer(standard="cedia")
    speaker_res = speaker_tool.calculate_vertical_angle(Ear_in, Tweet_in, SeatDist_ft)
    ear_tool = EarHeightValidator(design_height_in=42)
    ear_res = ear_tool.validate(Ear_in)
    rt60_tool = MaterialPresets()
    rt60_res = rt60_tool.calculate_rt60(L_ft, W_ft, H_ft, room.wall_material)
    modes = calculate_room_modes(L_ft, W_ft, H_ft)

    # --- C. PDF GENERATION (UPDATED LAYOUT) ---
    safe_client = "".join(x for x in room.client_name if x.isalnum() or x in " _-")
    # NEW FILENAME: Validation_Report instead of Audit
    filename = f"Validation_Report_{safe_client}.pdf"
    
    doc = SimpleDocTemplate(filename, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    # HEADER
    story.append(Paragraph(f"<b>{room.integrator_name.upper()}</b>", styles['Normal']))
    story.append(Spacer(1, 5)) # Reduced spacer
    story.append(Paragraph("AV SAFEGUARD DESIGN VALIDATION REPORT", styles['Heading1']))
    story.append(Paragraph("Pre-Construction Feasibility Assessment", styles['Heading2']))
    story.append(Spacer(1, 5)) 
    story.append(Paragraph(f"Client: {room.client_name} | Project: {room.project_name}", styles['Normal']))
    story.append(Paragraph("<b>Validated by: AV Safeguard</b>", styles['Normal']))
    story.append(Spacer(1, 10)) # Reduced spacer

    # SECTION 1: OPTICAL
    story.append(Paragraph("<b>1. OPTICAL ANALYSIS</b>", styles['Heading3']))
    data1 = [
        ["CHECK", "VALUE", "STANDARD", "STATUS"],
        ["Brightness", f"{FTL:.1f} fL", "SMPTE (16-22)", "PASS" if 16 <= FTL <= 22 else "WARN"],
        ["Throw Dist", f"Req: {Req_Throw:.1f}'", "Projector Spec", Throw_Pass],
        ["Vertical View", f"{Vert_View_Angle:.1f}\u00b0 (Up)", "Human Factors (<15\u00b0)", Vert_View_Pass]
    ]
    t1 = Table(data1, colWidths=[90, 140, 110, 80])
    t1.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    story.append(t1)
    story.append(Spacer(1, 10)) # Reduced spacer

    # SECTION 2: AUDIO
    story.append(Paragraph("<b>2. ACOUSTIC ANALYSIS</b>", styles['Heading3']))
    data2 = [
        ["CHECK", "DETAILS", "STANDARD", "STATUS"],
        ["Vert. Spkr Angle", f"{speaker_res['angle_deg']}\u00b0 Offset", "Dolby (<15\u00b0)", speaker_res['status']],
        ["Horiz. Spkr Angle", f"{Horiz_Angle:.1f}\u00b0 Offset", "Imaging (<10\u00b0)", Horiz_Pass],
        ["RT60 Reverb", f"{rt60_res['rt60']}s", "ITU-R (<0.6s)", rt60_res['status']],
        ["Ear Height", f"{ear_res['message']}", "Ergonomics", ear_res['status']]
    ]
    t2 = Table(data2, colWidths=[90, 140, 110, 80])
    t2.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    story.append(t2)
    story.append(Spacer(1, 10)) # Reduced spacer

    # SECTION 3: MODES & DIAGRAM
    story.append(Paragraph("<b>3. ROOM MODES & DIAGRAM</b>", styles['Heading3']))
    story.append(Paragraph(f"<b>Resonant Frequencies (Bass):</b> {modes['L']} Hz", styles['Normal']))
    story.append(Spacer(1, 10))
    
    # Draw Diagram (Now Compact)
    story.append(draw_room_diagram(L_ft, ScreenW_ft, SeatDist_ft, Req_Throw))
    
    # BUILD PDF WITH FOOTER
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)

    return {
        "pdf_url": filename,
        "results": {
            "throw": Throw_Pass,
            "brightness": f"{FTL:.1f} fL",
            "rt60": rt60_res['status'],
            "vertical_angle": speaker_res['status'],
            "horizontal_angle": Horiz_Pass,
            "ear_height": ear_res['status']
        }
    }
@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/{filename}")
async def get_pdf(filename: str):
    return FileResponse(filename, headers={"Content-Disposition": f"inline; filename={filename}"})