import sqlite3
import json

db_path = "data/gold.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Content ID 9 - Replace with Maura Murray
maura_hook = "She crashed her car in the dark. Then she simply disappeared."
maura_script = """On February 9, 2004, Maura Murray was 21 years old and studying nursing at the University of Massachusetts Amherst. That day, she withdrew $280 from an ATM around 3:30 p.m. in North Hadley, Massachusetts. Hours later, a neighbor, a school bus driver, spotted her black Saturn sedan parked on the side of Route 112 in Haverhill, New Hampshire. He said he approached her, offered to call for help, and she declined. When police arrived minutes later, Maura was gone. Despite two decades of searching, there has been no trace of her. Her case remains one of New England's most perplexing disappearances. The New Hampshire Cold Case Unit still investigates daily. Maura's family believes she was a victim of foul play. What happened on that dark New Hampshire road remains unknown."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 9",
    ("A UMass Student Vanished Without a Trace - 22 Years Unsolved", maura_hook, maura_script))

# Content ID 12 - Replace with Asha Degree
asha_hook = "She packed her backpack and left home on a rainy February night."
asha_script = """On February 14, 2000, nine-year-old Asha Jaquilla Degree packed a small backpack and left her home in Shelby, North Carolina, during early morning hours. Why she left remains a mystery. She was last seen by motorists walking along Highway 18 in heavy rain and wind. When one driver tried to stop and help her, Asha ran into the nearby woods. Her parents discovered her missing later that morning. For 25 years, she has never been found. Her bookbag was discovered buried at a construction site months later, along with a borrowed copy of "McElligot's Pool" and a New Kids on the Block concert T-shirt. In 2024, law enforcement executed search warrants in connection with the case, but no arrests have been made. Asha Degree deserves to be remembered not as a missing person, but as a child with hopes and dreams that were stolen from her that night. Her family still searches for answers."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 12",
    ("A 9-Year-Old Ran Into the Rain - And Was Never Seen Again", asha_hook, asha_script))

# Content ID 15 - Replace with Mollie Tibbetts
mollie_hook = "She left for an evening run and never came home."
mollie_script = """On July 18, 2018, Mollie Cecilia Tibbetts, a 20-year-old University of Iowa psychology student, left her boyfriend's home for an evening jog. She never returned. Mollie worked as a counselor at a day camp and was known for her kindness and dedication to children's safety. That night, surveillance footage captured a black Chevy Malibu following her on the rural Brooklyn, Iowa roads. One month later, investigators discovered Mollie's body in a cornfield miles from her home. Cristhian Bahena Rivera, a farm worker, was arrested and confessed to the murder. He received a life sentence in 2021. What troubled authorities was the nature of her death and the deliberate concealment of her body. Mollie Tibbetts was more than a tragic headline. She was a daughter, a student, and someone who wanted to help others. Her case serves as a stark reminder that danger can emerge from unexpected places, even on familiar roads."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 15",
    ("The College Student Who Went Jogging and Disappeared", mollie_hook, mollie_script))

# Content ID 20 - Replace with Missy Bevers
missy_hook = "She arrived early to teach her class. Her students found her dead."
missy_script = """On April 18, 2016, Terri Leann "Missy" Bevers, a 45-year-old fitness instructor and mother of three, arrived at Creekside Church of Christ in Midlothian, Texas around 4:30 a.m. to prepare for her early morning fitness class. Thirty minutes later, her students walked in to discover her body. Missy had suffered puncture wounds to her head and chest in what authorities determined was a homicide. Surveillance footage revealed a suspect in full tactical gear, including a SWAT-style outfit, vandalizing the church for approximately 30 minutes before Missy arrived. The suspect had a distinctive outward-turned gait, but their identity remains unknown nearly a decade later. Despite receiving over 3,000 tips and a $150,000 reward offered by Crime Stoppers, no one has been charged. Missy Bevers taught because she loved helping others become healthier and stronger. She deserved better than to die in the place where she served her community. Her case remains a haunting reminder that justice delayed is still justice sought."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 20",
    ("The Fitness Instructor Murdered Inside Her Church", missy_hook, missy_script))

# Content ID 23 - Replace with Jennifer Fairgate
jennifer_hook = "She checked in with a fake name. Three days later, she was dead."
jennifer_script = """In May 1995, a woman checked into the Oslo Plaza Hotel in Norway using the alias Jennifer Fairgate. She carried identification and credit cards under this name, but every trace of her identity was meticulously hidden. She had removed the labels from all her clothing. Three days after checking in, hotel staff found her dead in her room with a gunshot wound to her head and a 9mm pistol by her side. Authorities ruled her death a suicide, but the evidence suggests otherwise. An autopsy revealed undigested food in her stomach—the same food she had ordered from room service 24 hours before her death. This contradicts the timeline that should accompany a suicide by gunshot. More than thirty years later, Jennifer Fairgate's true identity remains unknown. No family came forward. No one claimed her body. Who was she? Why did she use a false name? The mystery continues to haunt Norwegian cold case investigators. Her story deserves to be solved—she deserves to be remembered by her real name."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 23",
    ("The Woman with No Past Found Dead in a Hotel Room", jennifer_hook, jennifer_script))

# Content ID 24 - Replace with expanded Asha Degree
asha2_hook = "She left home in a rainstorm and vanished for 25 years."
asha2_script = """Asha Degree should have been worried about Valentine's Day cards and school lunch. Instead, on February 14, 2000, the nine-year-old left her home in Shelby, North Carolina, in the middle of the night during a severe rainstorm. She packed a small backpack and walked toward Highway 18. Why she left remains one of the deepest mysteries in American crime. A motorist saw her at 1:30 a.m., walking in heavy rain and wind. When he stopped to offer help, Asha ran into the woods and disappeared. What followed was one of the most intensive missing children investigations in North Carolina history. Her backpack was discovered buried at a construction site months later, containing a borrowed Dr. Seuss book and her New Kids on the Block concert T-shirt—items a child would treasure. In 2024, police executed new search warrants and brought dogs to properties in three counties. No arrests have been made. Asha Degree was a real child with dreams and fears like any other nine-year-old. She deserves more than to be a cold case number. Law enforcement continues to search. Maybe you have answers. Asha's family never gave up hope."""

cursor.execute("UPDATE content SET title = ?, hook = ?, script = ? WHERE id = 24",
    ("The 9-Year-Old Girl Who Walked Into the Darkness", asha2_hook, asha2_script))

conn.commit()
print("All 6 scripts updated with factual cold cases.")
conn.close()
