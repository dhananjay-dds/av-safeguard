import os
import math
import uuid
import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Literal

# --- PDF LIBRARIES ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- DATA MODEL ---
class RoomData(BaseModel):
    # Metadata (Defaults are empty strings now, handled in logic)
    client_name: str = ""
    project_name: str = ""
    integrator_name: str = ""
    
    # Physics
    measurement_unit: Literal["Meters", "Feet"] = "Meters"
    length: float
    width: float
    height: float = 3.0
    screen_width: float
    screen_aspect_ratio: float = 1.777
    screen_gain: float = 1.0
    projector_lumens: int
    throw_ratio_min: float = 1.5
    throw_ratio_max: float = 2.0
    seating_distance: float = 4.0
    screen_mount_offset: float = 0.5
    ambient_light: str = "Dark Theater"

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
    d.add(String(10, screen_y_center - (screen_h_draw/2) - 10, "SCREEN", fontSize=8, fillColor=colors.blue))

    # 3. Seat
    seat_x = seat_dist_ft * scale
    d.add(Circle(seat_x, screen_y_center, 5, fillColor=colors.orange, strokeColor=colors.black))
    d.add(String(seat_x - 10, screen_y_center - 15, f"SEAT ({seat_dist_ft:.1f}')", fontSize=8))

    # 4. Throw Beam
    req_x = req_throw_min * scale
    beam_color = colors.green if avail_throw >= req_throw_min else colors.red
    status_text = "PASS" if avail_throw >= req_throw_min else "FAIL"

    d.add(Line(req_x, screen_y_center, 5, screen_y_center + (screen_h_draw/2), strokeColor=beam_color, strokeDashArray=[2,2])) 
    d.add(Line(req_x, screen_y_center, 5, screen_y_center - (screen_h_draw/2), strokeColor=beam_color, strokeDashArray=[2,2]))
    d.add(String(req_x, screen_y_center + 15, f"REQ: {req_throw_min:.1f}'", fontSize=8, fillColor=beam_color))
    
    return d

# --- API ENDPOINT ---
@app.post("/report")
async def get_report(room: RoomData):
    to_ft = 3.28084 if room.measurement_unit == "Meters" else 1.0
    
    # Handle Defaults if Empty
    final_client = room.client_name if room.client_name else "Valued Client"
    final_project = room.project_name if room.project_name else "Home Cinema"
    final_integrator = room.integrator_name if room.integrator_name else "AV Design Engine"

    # Calculations
    area = (room.screen_width * to_ft) * ((room.screen_width * to_ft) / room.screen_aspect_ratio)
    ftl = (room.projector_lumens * room.screen_gain) / area
    req_dist = (room.screen_width * to_ft) * room.throw_ratio_min
    avail_dist = (room.length * to_ft) - (room.screen_mount_offset * to_ft)
    throw_pass = avail_dist >= req_dist
    angle = math.degrees(2 * math.atan(((room.screen_width * to_ft) / 2) / (room.seating_distance * to_ft)))

    # PDF Generation
    filename = f"report_{uuid.uuid4()}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    
    # FIX: Set the PDF Title Metadata (Shows in Browser Tab)
    doc.title = f"Report - {final_client}"
    
    story = []
    styles = getSampleStyleSheet()

    # Header
    story.append(Paragraph(f"<b>{final_integrator.upper()}</b>", styles['Normal']))
    
    separator = Drawing(450, 5)
    separator.add(Line(0, 0, 450, 0))
    story.append(separator)

    story.append(Spacer(1, 10))
    story.append(Paragraph("AV DESIGN SAFEGUARD REPORT", styles['Heading1']))
    story.append(Paragraph(f"Client: {final_client} | Project: {final_project}", styles['Normal']))
    story.append(Spacer(1, 20))

    # Table
    data = [
        ["CHECK", "VALUE", "STATUS"],
        ["Brightness", f"{ftl:.1f} fL", "PASS" if 16 <= ftl <= 22 else "WARNING"],
        ["Throw Dist", f"Req: {req_dist:.1f}' | Avail: {avail_dist:.1f}'", "PASS" if throw_pass else "FAIL"],
        ["View Angle", f"{angle:.1f} degrees", "PASS" if 30 <= angle <= 60 else "CHECK"]
    ]
    t = Table(data, colWidths=[100, 200, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    if not throw_pass: t.setStyle(TableStyle([('BACKGROUND', (2,2), (2,2), colors.red)]))
    story.append(t)
    story.append(Spacer(1, 20))
    
    # Diagram
    story.append(draw_room_diagram(room.length*to_ft, room.screen_width*to_ft, room.seating_distance*to_ft, room.throw_ratio_min, room.throw_ratio_max, avail_dist, req_dist))
    
    # Assumptions
    story.append(Spacer(1, 30))
    story.append(Paragraph("<b>ASSUMPTIONS:</b> On-axis gain only. Throw dist excludes chassis depth.", styles['Normal']))

    doc.build(story)

    return {
        "pdf_url": filename,
        "calculations": {
            "ftl": round(ftl, 1),
            "brightness_status": "PASS" if 16 <= ftl <= 22 else "FAIL",
            "throw_status": "PASS" if throw_pass else "FAIL",
            "throw_msg": "Fits" if throw_pass else "Too Shallow",
            "viewing_angle": round(angle, 1),
            "angle_status": "PASS"
        }
    }

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html") as f: return f.read()

@app.get("/{filename}")
async def get_pdf(filename: str):
    return FileResponse(filename, headers={"Content-Disposition": "inline"})

@app.get("/favicon.ico")
async def favicon():
    return ""