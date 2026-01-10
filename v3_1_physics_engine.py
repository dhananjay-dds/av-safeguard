import math

# ==========================================
# FEATURE 1: SPEAKER ALIGNMENT (Vertical + Horizontal)
# ==========================================
class CenterChannelAnalyzer:
    """
    Analyzes center channel alignment (Vertical + Horizontal).
    Standard: CEDIA (Default) or Dolby.
    """
    
    STANDARDS = {
        "cedia": {
            "name": "CEDIA (Home Theater)",
            "vertical_optimal": 5,
            "vertical_max": 12,
            "horizontal_max": 0  # Should be centered
        },
        "dolby": {
            "name": "Dolby Atmos (Commercial)",
            "vertical_optimal": 10,
            "vertical_max": 15,
            "horizontal_max": 30 # +/- 30 degrees allowed
        }
    }
    
    def __init__(self, standard="cedia"):
        self.thresholds = self.STANDARDS[standard]

    def calculate_vertical_angle(self, ear_height_in, tweeter_height_in, dist_ft):
        """Calculates vertical angle from ear to tweeter."""
        vertical_dist_ft = (tweeter_height_in - ear_height_in) / 12.0
        angle_rad = math.atan(abs(vertical_dist_ft) / dist_ft)
        angle_deg = math.degrees(angle_rad)
        
        if angle_deg <= self.thresholds["vertical_optimal"]:
            status = "OPTIMAL"
        elif angle_deg <= self.thresholds["vertical_max"]:
            status = "ACCEPTABLE"
        else:
            status = "FAIL"
            
        return {
            "angle_deg": round(angle_deg, 1),
            "status": status,
            "offset_inches": round(vertical_dist_ft * 12, 1),
            "direction": "ABOVE ear" if vertical_dist_ft > 0 else "BELOW ear"
        }

    def calculate_horizontal_offset(self, offset_from_center_inches, dist_ft):
        """
        Calculates horizontal offset angle (Left/Right shift).
        """
        offset_ft = offset_from_center_inches / 12.0
        angle_rad = math.atan(abs(offset_ft) / dist_ft)
        angle_deg = math.degrees(angle_rad)
        
        # CEDIA prefers 0, but Dolby allows 30. We use 10 as a soft limit for home.
        limit = 10 if self.thresholds["name"] == "CEDIA (Home Theater)" else 30
        
        status = "PASS" if angle_deg <= limit else "FAIL"
        
        return {
            "angle_deg": round(angle_deg, 1),
            "status": status,
            "limit_deg": limit
        }

# ==========================================
# FEATURE 2: EAR HEIGHT TOLERANCE
# ==========================================
class EarHeightValidator:
    """
    Validates ear height with tolerance buffers (Soft Warnings).
    Design Target: 42 inches (Standard).
    """
    
    def __init__(self, design_height_in=42):
        self.design_height = design_height_in

    def validate(self, user_ear_height_in):
        deviation = abs(user_ear_height_in - self.design_height)
        
        if deviation <= 1:
            zone = "OPTIMAL"
            msg = "Perfect match"
        elif deviation <= 2:
            zone = "ACCEPTABLE" 
            msg = "Within tolerance (Soft Warning)"
        elif deviation <= 3:
            zone = "MARGINAL"
            msg = "Consider riser adjustment (+/- 1 inch)"
        else:
            zone = "FAIL"
            msg = "Significant height mismatch"
            
        return {
            "user_height": user_ear_height_in,
            "deviation": round(deviation, 1),
            "status": zone,
            "message": msg
        }

# ==========================================
# FEATURE 3: RT60 PRESETS
# ==========================================
class MaterialPresets:
    """
    RT60 Calculation using friendly Presets.
    """
    
    PRESETS = {
        "drywall_shell": {"coeff": 0.05, "name": "Drywall Shell (Untreated)"},
        "concrete_glass": {"coeff": 0.03, "name": "Concrete + Glass (Worst Case)"},
        "carpet_painted": {"coeff": 0.15, "name": "Carpet + Painted Walls"},
        "treated_50": {"coeff": 0.45, "name": "50% Acoustic Treatment"},
        "fully_treated": {"coeff": 0.70, "name": "Fully Treated Cinema"}
    }
    
    def calculate_rt60(self, l_ft, w_ft, h_ft, preset_key):
        if preset_key not in self.PRESETS:
            return {"error": "Invalid preset"}
            
        data = self.PRESETS[preset_key]
        coeff = data["coeff"]
        
        volume = l_ft * w_ft * h_ft
        surface_area = 2 * (l_ft*w_ft + l_ft*h_ft + w_ft*h_ft)
        
        # Eyring Formula
        try:
            rt60 = (0.161 * volume) / (surface_area * -math.log(1 - coeff))
        except:
            rt60 = 9.99 # Catch divide by zero or log errors
            
        if rt60 <= 0.6: status = "PASS"
        elif rt60 <= 1.2: status = "WARNING"
        else: status = "FAIL"
        
        return {
            "rt60": round(rt60, 2),
            "status": status,
            "material_name": data["name"],
            "target": "0.3 - 0.6s"
        }