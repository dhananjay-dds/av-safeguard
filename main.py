import os
import math
import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Literal

# --- PDF LIBRARIES ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- DATA MODEL (V3 UPGRADED) ---
class RoomData(BaseModel):
    # Metadata
    client_name: str = ""
    project_name: str = ""
    integrator_name: str = ""
    
    # Physics - Dimensions
    measurement_unit: Literal["Meters", "Feet"] = "Meters"
    length: float
    width: float
    height: float = 3.0
    
    # Physics - Screen & Projector
    screen_width: float
    screen_aspect_ratio: float = 1.777
    screen_gain: float = 1.0  
    projector_lumens: int
    throw_ratio_min: float = 1.5
    throw_ratio_max: float = 2.0
    screen_mount_offset: float = 0.5
    
    # Physics - Seating & Audio (NEW IN V3)
    seating_distance: float = 4.0
    sofa_width: float = 8.0          # Default 8ft sofa
    center_speaker_height: float = 3.0 # Height from floor (ft)
    ear_height: float = 3.5          # Standard seated ear height (ft)
    ambient_light: str = "Dark Theater"

# --- V3 ENGINEERING LOGIC ---

# 1. HVAC NOISE CHECK
def check_hvac_noise(room_vol_ft3):
    if room_vol_ft3 > 5000:
        return "CRITICAL: Large room volume (>5000ft³). Standard HVAC will be audible. Dedicated NC-30 High-Static unit required."
    elif room_vol_ft3 > 2000:
        return "WARNING: Standard HVAC (NC-45) likely too loud for this volume. Specify In-Line Silencers or Upgrade to NC-30."
    else:
        return "PASS: Standard HVAC acceptable, but dedicated zoning recommended for noise isolation."

# 2. ROOM MODES
def calculate_room_modes(L, W, H):
    modes = {"L": [], "W": [], "H": []}
    for dim, label in [(L, "L"), (W, "W"), (H, "H")]:
        for n in range(1, 3): 
            freq = 1125 / (2 * dim) * n
            modes[label].append(round(freq, 1))
    return modes

# 3. OFF-AXIS & AUDIO GEOMETRY
def check_geometry(room: RoomData, to_ft):
    # A. Off-Axis Viewing Cone
    if room.screen_gain >= 1.5: max_angle = 15
    elif room.screen_gain >= 1.3: max_angle = 20
    else: max_angle = 30 # Matte White
    
    half_sofa = (room.sofa_width * to_ft) / 2
    seat_dist = room.seating_distance * to_ft
    # Protect against divide by zero
    if seat_dist == 0: seat_dist = 0.1
        
    off_axis_angle = math.degrees(math.atan(half_sofa / seat_dist))
    off_axis_status = "PASS" if off_axis_angle <= max_angle else "FAIL"
    
    # B. Vertical Audio Angle (Dolby Limit: 15 degrees)
    height_diff = abs((room.center_speaker_height * to_ft) - (room.ear_height * to_ft))
    audio_angle = math.degrees(math.atan(height_diff / seat_dist))
    audio_status = "PASS" if audio_angle <= 15 else "FAIL"
    
    return {
        "off_axis_angle": round(off_axis_angle, 1),
        "off_axis_limit": max_angle,
        "off_axis_status": off_axis_status,
        "audio_angle": round(audio_angle, 1),
        "audio_status": audio_status
    }

# --- DIAGRAM ENGINE ---
def draw_room_diagram(room_len_ft, screen_width_ft, seat_dist_ft, tr_min, tr_max, avail_throw, req_throw_min):
    d = Drawing(400, 200)
    scale = 350 / max(room_len_ft, 20) 
    
    # 1. Room
    room_w = room_len_ft * scale
    room_h = 10 * scale 
    y_start = 100 - (room_h / 2)
    d.add(Rect(0, y_start, room_w, room_h, fillColor=colors.whitesmoke, strokeColor=colors.black))
    d.add(String(10, y_start - 10, f"ROOM DEPTH: {room_len_ft:.1f}'", fontSize=8))

    # 2. Screen
    screen_h_draw = (screen_width_ft / 1.77) * scale 
    screen_y_center = 100 
    d.add(Line(5, screen_y_center - (screen_h_draw/2), 5, screen_y_center + (screen_h_draw/2), strokeWidth=4, strokeColor=colors.blue))
    
    # 3. Seat
    seat_x = seat_dist_ft * scale
    d.add(Circle(seat_x, screen_y_center, 5, fillColor=colors.orange, strokeColor=colors.black))
    d.add(String(seat_x - 10, screen_y_center - 15, f"SEAT ({seat_dist_ft:.1f}')", fontSize=8))

    # 4. Throw Beam
    req_x = req_throw_min * scale
    beam_color = colors.green if avail_throw >= req_throw_min else colors.red
    d.add(Line(req_x, screen_y_center, 5, screen_y_center + (screen_h_draw/2), strokeColor=beam_color, strokeDashArray=[2,2])) 
    d.add(Line(req_x, screen_y_center, 5, screen_y_center - (screen_h_draw/2), strokeColor=beam_color, strokeDashArray=[2,2]))
    d.add(String(req_x, screen_y_center + 15, f"REQ: {req_throw_min:.1f}'", fontSize=8, fillColor=beam_color))
    
    return d

# --- MAIN API ENDPOINT (V3 UPGRADED) ---
@app.post("/report")
async def get_report(room: RoomData):
    to_ft = 3.28084 if room.measurement_unit == "Meters" else 1.0
    
    # Defaults
    final_client = room.client_name if room.client_name else "Valued Client"
    final_project = room.project_name if room.project_name else "Home Cinema"
    final_integrator = room.integrator_name if room.integrator_name else "AV Design Engine"

    # --- CALCULATIONS ---
    # 1. Brightness & Throw (V2)
    area = (room.screen_width * to_ft) * ((room.screen_width * to_ft) / room.screen_aspect_ratio)
    ftl = (room.projector_lumens * room.screen_gain) / area
    req_dist = (room.screen_width * to_ft) * room.throw_ratio_min
    avail_dist = (room.length * to_ft) - (room.screen_mount_offset * to_ft)
    throw_pass = avail_dist >= req_dist
    view_angle = math.degrees(2 * math.atan(((room.screen_width * to_ft) / 2) / (room.seating_distance * to_ft)))

    # 2. V3 Geometry Checks
    geo_data = check_geometry(room, to_ft)
    
    # 3. V3 Room Modes
    dims_ft = [room.length * to_ft, room.width * to_ft, room.height * to_ft]
    modes = calculate_room_modes(*dims_ft)
    
    # 4. V3 HVAC Check
    vol_ft3 = dims_ft[0] * dims_ft[1] * dims_ft[2]
    hvac_msg = check_hvac_noise(vol_ft3)

    # --- PDF GENERATION ---
    filename = f"report_{uuid.uuid4()}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    doc.title = f"Report - {final_client}"
    story = []
    styles = getSampleStyleSheet()

    # Title Block
    story.append(Paragraph(f"<b>{final_integrator.upper()}</b>", styles['Normal']))
    story.append(Drawing(450, 5).add(Line(0, 0, 450, 0)))
    story.append(Spacer(1, 10))
    story.append(Paragraph("AV ENGINEERING SAFEGUARD REPORT (V3)", styles['Heading1']))
    story.append(Paragraph(f"Client: {final_client} | Project: {final_project}", styles['Normal']))
    story.append(Spacer(1, 15))

    # SECTION 1: CORE PHYSICS
    story.append(Paragraph("<b>1. OPTICAL & THROW ANALYSIS</b>", styles['Heading3']))
    data = [
        ["CHECK", "VALUE", "STATUS"],
        ["Brightness", f"{ftl:.1f} fL", "PASS" if 16 <= ftl <= 22 else "WARNING"],
        ["Throw Dist", f"Req: {req_dist:.1f}' | Avail: {avail_dist:.1f}'", "PASS" if throw_pass else "FAIL"],
        ["View Angle", f"{view_angle:.1f}° (SMPTE)", "PASS" if 30 <= view_angle <= 60 else "CHECK"],
    ]
    t = Table(data, colWidths=[120, 200, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (2,1), (2,-1), 'CENTER'),
    ]))
    if not throw_pass: t.setStyle(TableStyle([('BACKGROUND', (2,2), (2,2), colors.red)]))
    story.append(t)
    story.append(Spacer(1, 15))

    # SECTION 2: V3 ADVANCED GEOMETRY
    story.append(Paragraph("<b>2. GEOMETRY & AUDIO ALIGNMENT</b>", styles['Heading3']))
    data_v3 = [
        ["CHECK", "DETAILS", "STATUS"],
        ["Off-Axis Seat", f"Angle: {geo_data['off_axis_angle']}° (Max {geo_data['off_axis_limit']}°)", geo_data['off_axis_status']],
        ["Center Channel", f"Vert Angle: {geo_data['audio_angle']}° (Max 15°)", geo_data['audio_status']],
    ]
    t_v3 = Table(data_v3, colWidths=[120, 200, 100])
    t_v3.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.dimgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (2,1), (2,-1), 'CENTER'),
    ]))
    if geo_data['off_axis_status'] == "FAIL": t_v3.setStyle(TableStyle([('BACKGROUND', (2,1), (2,1), colors.red)]))
    if geo_data['audio_status'] == "FAIL": t_v3.setStyle(TableStyle([('BACKGROUND', (2,2), (2,2), colors.red)]))
    story.append(t_v3)
    story.append(Spacer(1, 15))

    # SECTION 3: ROOM MODES
    story.append(Paragraph("<b>3. ACOUSTIC ROOM MODES (HERO FEATURE)</b>", styles['Heading3']))
    story.append(Paragraph("<i>These frequencies will naturally resonate ('boom') in this room.</i>", styles['Normal']))
    story.append(Spacer(1, 5))
    mode_text = f"<b>Length Modes:</b> {', '.join(map(str, modes['L']))} Hz<br/><b>Width Modes:</b> {', '.join(map(str, modes['W']))} Hz<br/><b>Height Modes:</b> {', '.join(map(str, modes['H']))} Hz"
    story.append(Paragraph(mode_text, styles['Normal']))
    story.append(Spacer(1, 15))

    # SECTION 4: HVAC
    story.append(Paragraph("<b>4. HVAC NOISE SPECIFICATION</b>", styles['Heading3']))
    story.append(Paragraph(hvac_msg, styles['Normal']))
    story.append(Spacer(1, 20))

    # Diagram
    story.append(draw_room_diagram(room.length*to_ft, room.screen_width*to_ft, room.seating_distance*to_ft, room.throw_ratio_min, room.throw_ratio_max, avail_dist, req_dist))

    doc.build(story)

    return {
        "pdf_url": filename,
        "calculations": {
            "ftl": round(ftl, 1),
            "brightness_status": "PASS" if 16 <= ftl <= 22 else "FAIL",
            "throw_status": "PASS" if throw_pass else "FAIL",
            "angle_status": "PASS",
            "off_axis_status": geo_data['off_axis_status'],
            "audio_status": geo_data['audio_status']
        }
    }

# --- THE MISSING PART: ROOT & STATIC FILES ---
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html") as f: return f.read()

@app.get("/{filename}")
async def get_pdf(filename: str):
    return FileResponse(filename, headers={"Content-Disposition": "inline"})