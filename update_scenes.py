import sqlite3
import json

db_path = "data/gold.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# ID 9: Maura Murray
maura_scenes = [
    {"search_keywords": "dark mountain road night", "image_prompt": "Dark New Hampshire mountain road at night, single car parked on shoulder, dramatic shadows cast by headlights, wet pavement reflecting light, moody documentary style", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "FEBRUARY 9, 2004"},
    {"search_keywords": "black saturn car accident", "image_prompt": "Black Saturn sedan partially visible in darkness on roadside, single streetlight casting long shadows, wet rain-soaked asphalt, atmospheric noir photography", "ken_burns": "pan_left", "duration": 5, "text_overlay": "ROUTE 112 - HAVERHILL"},
    {"search_keywords": "police search rescue", "image_prompt": "Police cars with flashing lights on dark rural road, fog in distance, search beams cutting through mist, documentary crime scene lighting", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "MAURA MURRAY, 21"},
    {"search_keywords": "missing person poster", "image_prompt": "Close-up of missing person flyer with photograph, weathered texture, dramatic single light source, dark background, cold case documentary aesthetic", "ken_burns": "zoom_in", "duration": 5, "text_overlay": ""},
    {"search_keywords": "mountains new hampshire forest", "image_prompt": "Dense New Hampshire forest at dusk, bare winter trees, deep shadows, misty atmosphere, documentary photography style, moody and mysterious", "ken_burns": "diagonal", "duration": 7, "text_overlay": "22 YEARS MISSING"},
    {"search_keywords": "atm cash withdrawal", "image_prompt": "Close-up of ATM machine in darkness, screen glowing, money slot visible, dramatic single light, forensic investigation aesthetic", "ken_burns": "zoom_pan_combo", "duration": 6, "text_overlay": "$280 WITHDRAWN"},
    {"search_keywords": "cold case detective office", "image_prompt": "Dark detective office with case files, wall covered with investigation photos, single desk lamp, noir investigative atmosphere", "ken_burns": "pan_right", "duration": 6, "text_overlay": "STILL INVESTIGATING"},
    {"search_keywords": "university campus building", "image_prompt": "Moody shot of university building at night, dramatic architectural lighting, dark windows, academic atmosphere, noir documentary style", "ken_burns": "zoom_out", "duration": 5, "text_overlay": "UMASS AMHERST"},
    {"search_keywords": "snowy road winter", "image_prompt": "Desolate winter road covered in snow, bare trees on both sides, dark overcast sky, isolated and eerie atmosphere, atmospheric documentary photography", "ken_burns": "pan_left", "duration": 6, "text_overlay": ""}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 9", (json.dumps(maura_scenes),))

# ID 12: Asha Degree
asha_scenes = [
    {"search_keywords": "rainy night highway", "image_prompt": "Dark North Carolina Highway 18 in heavy rain at night, streetlights reflecting off wet pavement, atmospheric mist, documentary noir style", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "FEBRUARY 14, 2000"},
    {"search_keywords": "rain storm wind dark", "image_prompt": "Severe rainstorm with wind-blown rain, dark landscape barely visible, dramatic atmospheric lighting, ominous weather documentation", "ken_burns": "pan_right", "duration": 5, "text_overlay": "SHELBY, NORTH CAROLINA"},
    {"search_keywords": "child backpack belongings", "image_prompt": "Small child's backpack on dark surface, personal items visible, forensic evidence lighting, documentary crime photography", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "ASHA DEGREE, AGE 9"},
    {"search_keywords": "forest woods dark", "image_prompt": "Dense dark woods at night, bare branches creating patterns of shadow, mist between trees, mysterious forest atmosphere", "ken_burns": "diagonal", "duration": 7, "text_overlay": ""},
    {"search_keywords": "missing child poster", "image_prompt": "Close-up of missing child poster with young girl's photograph, weathered appearance, dramatic lighting, emotional documentary aesthetic", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "25 YEARS MISSING"},
    {"search_keywords": "seuss book children", "image_prompt": "Worn children's book on dark surface, detailed cover visible, forensic evidence style lighting, nostalgic documentary photography", "ken_burns": "zoom_pan_combo", "duration": 5, "text_overlay": "MCELIGGOT'S POOL"},
    {"search_keywords": "police search warrant", "image_prompt": "Police officers conducting ground search with dogs, dark atmospheric conditions, investigative documentation style", "ken_burns": "pan_left", "duration": 6, "text_overlay": "2024 - NEW SEARCH"},
    {"search_keywords": "construction site night", "image_prompt": "Dark abandoned construction site at night, partial equipment visible, shadows and deep darkness, mysterious documentary tone", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "BACKPACK FOUND BURIED"},
    {"search_keywords": "missing persons investigation", "image_prompt": "Police investigation desk with files and evidence, overhead lamp creating dramatic shadows, noir detective aesthetic", "ken_burns": "diagonal", "duration": 5, "text_overlay": ""}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 12", (json.dumps(asha_scenes),))

# ID 15: Mollie Tibbetts
mollie_scenes = [
    {"search_keywords": "rural iowa cornfield", "image_prompt": "Vast Iowa cornfield at dusk, rural landscape, warm setting sun casting long shadows, agricultural documentary style", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "JULY 18, 2018"},
    {"search_keywords": "jogger running path", "image_prompt": "Rural running trail through countryside, dramatic evening lighting, atmospheric mood, documentary photography style", "ken_burns": "pan_left", "duration": 5, "text_overlay": "BROOKLYN, IOWA"},
    {"search_keywords": "black chevy malibu car", "image_prompt": "Dark Chevy Malibu on rural road, surveillance-style photograph, atmospheric lighting, investigative documentation", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "MOLLIE TIBBETTS, 20"},
    {"search_keywords": "surveillance video footage", "image_prompt": "Grainy security camera footage showing rural road, timestamp visible, investigative documentary aesthetic, high contrast", "ken_burns": "diagonal", "duration": 7, "text_overlay": "SURVEILLANCE FOOTAGE"},
    {"search_keywords": "cornfield discovery body", "image_prompt": "Close-up of cornfield with forensic markers, dark soil, investigative photography style, somber documentary tone", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "ONE MONTH LATER"},
    {"search_keywords": "police interrogation room", "image_prompt": "Dark institutional interrogation room, single overhead light, empty chairs, tense noir atmosphere", "ken_burns": "zoom_pan_combo", "duration": 5, "text_overlay": "SUSPECT INTERROGATED"},
    {"search_keywords": "university campus iowa", "image_prompt": "University of Iowa building at night, dramatic architectural lighting, academic noir documentary style", "ken_burns": "pan_right", "duration": 6, "text_overlay": "PSYCHOLOGY STUDENT"},
    {"search_keywords": "prison bars cells", "image_prompt": "Prison cell interior with metal bars casting sharp shadows, institutional lighting, justice served atmosphere", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "LIFE SENTENCE 2021"},
    {"search_keywords": "day camp children", "image_prompt": "Empty outdoor recreational space at dusk, benches visible, melancholy atmosphere, documentary photography style", "ken_burns": "pan_left", "duration": 5, "text_overlay": ""}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 15", (json.dumps(mollie_scenes),))

# ID 20: Missy Bevers
missy_scenes = [
    {"search_keywords": "church building exterior night", "image_prompt": "Creekside Church exterior at dawn, dramatic architectural lighting, early morning mist, documentary religious building photography", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "APRIL 18, 2016"},
    {"search_keywords": "fitness instructor workout", "image_prompt": "Empty fitness class space at dawn, exercise equipment visible, dramatic morning light through windows, documentary interior", "ken_burns": "pan_left", "duration": 5, "text_overlay": "MIDLOTHIAN, TEXAS"},
    {"search_keywords": "tactical swat gear", "image_prompt": "Surveillance footage of figure in tactical gear, distinctive gait visible, investigation documentation style, grainy quality", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "MISSY BEVERS, 45"},
    {"search_keywords": "crime scene vandalism", "image_prompt": "Church interior showing signs of disturbance, investigative photography, documentary forensic lighting", "ken_burns": "diagonal", "duration": 7, "text_overlay": "CRIME SCENE 4:30 AM"},
    {"search_keywords": "police investigation board", "image_prompt": "Investigation board with case photos and timeline, dramatic single light source, noir detective aesthetic", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "OVER 3000 TIPS"},
    {"search_keywords": "reward poster notice", "image_prompt": "Crime stoppers reward poster in darkness, text highlighted by dramatic lighting, documentary justice appeal", "ken_burns": "zoom_pan_combo", "duration": 5, "text_overlay": "$150,000 REWARD"},
    {"search_keywords": "mother of three family", "image_prompt": "Empty family photograph frame on dark surface, single spot light, emotional documentary aesthetic", "ken_burns": "pan_right", "duration": 6, "text_overlay": "MOTHER OF THREE"},
    {"search_keywords": "unsolved case files", "image_prompt": "Cold case file folder on detective's desk, dramatic lighting, investigative noir atmosphere", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "UNSOLVED"},
    {"search_keywords": "texas church community", "image_prompt": "Church sanctuary interior with pews visible, dawn light through windows, documentary religious setting", "ken_burns": "pan_left", "duration": 5, "text_overlay": ""}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 20", (json.dumps(missy_scenes),))

# ID 23: Jennifer Fairgate
jennifer_scenes = [
    {"search_keywords": "oslo plaza hotel norway", "image_prompt": "Elegant hotel building exterior at night, dramatic architectural lighting, European noir documentary style", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "MAY 1995"},
    {"search_keywords": "hotel room interior luxury", "image_prompt": "Hotel room showing elegant furniture and bed, dramatic single window light, noir documentary interior photography", "ken_burns": "pan_left", "duration": 5, "text_overlay": "OSLO, NORWAY"},
    {"search_keywords": "hotel registration desk", "image_prompt": "Empty hotel reception desk at night, professional but eerie atmosphere, documentary institutional setting", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "JENNIFER FAIRGATE"},
    {"search_keywords": "fake identification documents", "image_prompt": "Close-up of identity documents on dark surface, dramatic single light source, forensic investigation photography", "ken_burns": "diagonal", "duration": 7, "text_overlay": "FALSE IDENTITY"},
    {"search_keywords": "clothing labels removed", "image_prompt": "Close-up of clothing item with removed label, investigative forensic lighting, detailed documentary photography", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "ALL LABELS REMOVED"},
    {"search_keywords": "9mm pistol weapon", "image_prompt": "Close-up of handgun on dark surface, dramatic forensic lighting, evidence photograph style", "ken_burns": "zoom_pan_combo", "duration": 5, "text_overlay": "GUNSHOT WOUND"},
    {"search_keywords": "autopsy medical examination", "image_prompt": "Forensic laboratory with scientific equipment, cool blue lighting, clinical investigation atmosphere", "ken_burns": "pan_right", "duration": 6, "text_overlay": "AUTOPSY EVIDENCE"},
    {"search_keywords": "unsolved mystery files", "image_prompt": "Cold case investigation files spread on desk, dramatic shadows, noir detective aesthetic, 30 years unsolved", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "30 YEARS UNSOLVED"},
    {"search_keywords": "mystery identity unknown", "image_prompt": "Question mark symbol in darkness, ethereal lighting, symbolic documentary photography", "ken_burns": "pan_left", "duration": 5, "text_overlay": ""}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 23", (json.dumps(jennifer_scenes),))

# ID 24: Asha Degree expanded
asha2_scenes = [
    {"search_keywords": "valentine day night rainstorm", "image_prompt": "Dark rainy Valentine's Day night, stormy weather with rain and wind, dramatic atmospheric photography, ominous conditions", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "FEBRUARY 14, 2000"},
    {"search_keywords": "child bedroom home", "image_prompt": "Empty child's bedroom at night, single dim light visible, melancholy domestic atmosphere, documentary photography", "ken_burns": "pan_left", "duration": 5, "text_overlay": "SHELBY, NC - MIDNIGHT"},
    {"search_keywords": "backpack small child packed", "image_prompt": "Small packed backpack on dark surface, child-sized, forensic evidence lighting, emotional documentary style", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "ASHA DEGREE, AGE 9"},
    {"search_keywords": "highway 18 north carolina dark", "image_prompt": "NC Highway 18 in severe rainstorm, visibility poor, atmospheric conditions, dramatic weather documentation", "ken_burns": "diagonal", "duration": 7, "text_overlay": "HEAVY RAIN & WIND"},
    {"search_keywords": "motorist sees child", "image_prompt": "Car interior windshield view of dark highway in rain, headlights illuminating wet road, atmospheric documentary perspective", "ken_burns": "zoom_in", "duration": 6, "text_overlay": "1:30 AM SIGHTING"},
    {"search_keywords": "forest woods child fled", "image_prompt": "Dark dense woods with rain falling, entrance to tree line visible, mysterious atmospheric photography, foreboding mood", "ken_burns": "zoom_pan_combo", "duration": 5, "text_overlay": "CHILD FLED INTO WOODS"},
    {"search_keywords": "buried backpack discovery", "image_prompt": "Construction site excavation area, dark soil, buried items being uncovered, forensic investigation documentation", "ken_burns": "pan_right", "duration": 6, "text_overlay": "BACKPACK FOUND"},
    {"search_keywords": "police search dogs 2024", "image_prompt": "Police K9 unit conducting ground search in field, dramatic atmospheric conditions, active investigation documentation", "ken_burns": "zoom_out", "duration": 6, "text_overlay": "2024 SEARCH WARRANTS"},
    {"search_keywords": "missing 25 years family hope", "image_prompt": "Family home exterior at dusk with warm window light, emotional documentary architectural photography, hope and grief", "ken_burns": "pan_left", "duration": 5, "text_overlay": "25 YEARS MISSING"}
]
cursor.execute("UPDATE content SET scene_descriptions = ? WHERE id = 24", (json.dumps(asha2_scenes),))

conn.commit()
print("All scene descriptions updated with factual case details.")
conn.close()
