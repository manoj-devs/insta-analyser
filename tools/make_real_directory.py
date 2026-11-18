"""Builds app/seed/influencer_directory.csv: REAL public figures with the follower count and date printed by the named public page.
Nothing here is invented. avg_likes / avg_comments are left blank because those pages do not publish them (the app then uses the typical engagement for the size).
Add more rows by editing ROWS (or upload a CSV in Admin > Regions) and run:  python tools/make_real_directory.py"""
import csv, os
H = ["handle", "display_name", "continent", "country", "state_or_region", "city", "category", "account_type", "verified", "followers", "avg_likes", "avg_comments", "posts_per_week", "as_of", "source"]
SC = "socialcrawl.dev live ranking page"
R = lambda h, n, co, cn, st, ci, cat, ty, f, d, s: [h, n, co, cn, st, ci, cat, ty, 1, f, "", "", "", d, s]
ROWS = [
 # world: socialcrawl.dev, page dated 2026-11-17
 R("cristiano", "Cristiano Ronaldo", "Europe", "Portugal", "", "", "sports", "athlete", 681060707, "2026-11-17", SC),
 R("leomessi", "Lionel Messi", "South America", "Argentina", "", "", "sports", "athlete", 517336437, "2026-11-17", SC),
 R("selenagomez", "Selena Gomez", "North America", "United States", "", "", "music", "celebrity", 402009841, "2026-11-17", SC),
 R("kyliejenner", "Kylie Jenner", "North America", "United States", "", "", "fashion_&_style", "celebrity", 381031695, "2026-11-17", SC),
 R("therock", "Dwayne Johnson", "North America", "United States", "", "", "film_tv_&_video", "celebrity", 379909453, "2026-11-17", SC),
 R("arianagrande", "Ariana Grande", "North America", "United States", "", "", "music", "celebrity", 362034480, "2026-11-17", SC),
 R("kimkardashian", "Kim Kardashian", "North America", "United States", "", "", "celebrity_&_pop_culture", "celebrity", 343559677, "2026-11-17", SC),
 R("beyonce", "Beyonce", "North America", "United States", "", "", "music", "celebrity", 298277957, "2026-11-17", SC),
 R("khloekardashian", "Khloe Kardashian", "North America", "United States", "", "", "celebrity_&_pop_culture", "celebrity", 291081096, "2026-11-17", SC),
 R("kendalljenner", "Kendall Jenner", "North America", "United States", "", "", "fashion_&_style", "celebrity", 277519604, "2026-11-17", SC),
 # India: film
 R("shraddhakapoor", "Shraddha Kapoor", "Asia", "India", "Maharashtra", "Mumbai", "film_tv_&_video", "celebrity", 94200000, "2025", "bosswallah.com top-10 India (2025)"),
 R("priyankachopra", "Priyanka Chopra", "Asia", "India", "", "", "film_tv_&_video", "celebrity", 92500000, "2025", "bosswallah.com top-10 India (2025)"),
 R("aliaabhatt", "Alia Bhatt", "Asia", "India", "Maharashtra", "Mumbai", "film_tv_&_video", "celebrity", 86200000, "2025", "bosswallah.com top-10 India (2025)"),
 R("samantharuthprabhu", "Samantha Ruth Prabhu", "Asia", "India", "", "", "film_tv_&_video", "celebrity", 35300000, "2025", "deccanchronicle.com Tollywood list"),
 R("alluarjunonline", "Allu Arjun", "Asia", "India", "", "", "film_tv_&_video", "celebrity", 26400000, "2025", "deccanchronicle.com Tollywood list"),
 # India: cricket and sport
 R("virat.kohli", "Virat Kohli", "Asia", "India", "Delhi", "", "sports", "athlete", 274000000, "2026-01-23", "newsable.asianetnews.com (23 Jan 2026)"),
 R("sachintendulkar", "Sachin Tendulkar", "Asia", "India", "Maharashtra", "Mumbai", "sports", "athlete", 51400000, "2026", "utilities-online.info cricketers list (2026)"),
 R("mahi7781", "MS Dhoni", "Asia", "India", "", "", "sports", "athlete", 49700000, "2026", "utilities-online.info cricketers list (2026)"),
 R("rohitsharma45", "Rohit Sharma", "Asia", "India", "Maharashtra", "Mumbai", "sports", "athlete", 46000000, "2026", "utilities-online.info cricketers list (2026)"),
 R("hardikpandya93", "Hardik Pandya", "Asia", "India", "Gujarat", "", "sports", "athlete", 45300000, "2026", "utilities-online.info cricketers list (2026)"),
 R("jaspritbumrah93", "Jasprit Bumrah", "Asia", "India", "Gujarat", "", "sports", "athlete", 22400000, "2026", "utilities-online.info cricketers list (2026)"),
 R("neeraj____chopra", "Neeraj Chopra", "Asia", "India", "Haryana", "Panipat", "sports", "athlete", 9570000, "2026-07", "socialveins.com (updated July 2026)"),
 R("pvsindhu1", "PV Sindhu", "Asia", "India", "", "", "sports", "athlete", 3730000, "2026-07", "socialveins.com (updated July 2026)"),
 # India: creators
 R("jannatzubair29", "Jannat Zubair", "Asia", "India", "", "", "film_tv_&_video", "creator", 49600000, "2026-05", "ishort-pp.web.app Indian reels creators (early May 2026)"),
 R("avneetkaur_13", "Avneet Kaur", "Asia", "India", "", "", "film_tv_&_video", "creator", 31700000, "2026-05", "ishort-pp.web.app Indian reels creators (early May 2026)"),
 R("ashishchanchlani", "Ashish Chanchlani", "Asia", "India", "Maharashtra", "Mumbai", "film_tv_&_video", "creator", 29000000, "2026-11", "starngage.com India ranking (2026-11)"),
 R("bhuvan.bam22", "Bhuvan Bam", "Asia", "India", "Delhi", "", "film_tv_&_video", "creator", 22200000, "2026-05", "ishort-pp.web.app Indian reels creators (early May 2026)"),
 R("mostlysane", "Prajakta Koli", "Asia", "India", "Maharashtra", "Mumbai", "film_tv_&_video", "creator", 8800000, "2025", "exlyapp.com top creators (2025)"),
 R("beerbiceps", "Ranveer Allahbadia", "Asia", "India", "Maharashtra", "Mumbai", "diaries_&_daily_life", "creator", 4440000, "2026-07", "socialveins.com (updated July 2026)"),
 R("kushakapila", "Kusha Kapila", "Asia", "India", "Delhi", "", "fashion_&_style", "creator", 4400000, "2026-01", "hireinfluence.com (29 Jan 2026)"),
 R("komalpandeyofficial", "Komal Pandey", "Asia", "India", "Maharashtra", "Mumbai", "fashion_&_style", "creator", 2100000, "2026", "digitalgriot.com top influencers (2026)"),
 # Tamil Nadu
 R("actorvijay", "Vijay", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "celebrity", 12700000, "2024-12-27", "filmibeat.com Kollywood list (27 Dec 2024)"),
 R("actorsuriya", "Suriya", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "celebrity", 9800000, "2024-12-27", "filmibeat.com Kollywood list (27 Dec 2024)"),
 R("dhanushkraja", "Dhanush", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "celebrity", 7700000, "2024-12-27", "filmibeat.com Kollywood list (27 Dec 2024)"),
 R("sivaangi.krish", "Sivaangi Krishnakumar", "Asia", "India", "Tamil Nadu", "Chennai", "music", "creator", 6240000, "2026-07", "socialveins.com (updated July 2026)"),
 R("singerkrish", "Krishh Balakrishnan", "Asia", "India", "Tamil Nadu", "Chennai", "music", "creator", 760200, "2026-07", "socialveins.com (updated July 2026)"),
 # Tamil Nadu: Chennai creators (category is approximate)
 R("tamiltrekker", "Bhuvanidharan", "Asia", "India", "Tamil Nadu", "Chennai", "travel_&_adventure", "creator", 435100, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("erumasaani", "Eruma Saani", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 354000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("dk00019", "Dinesh Karthik", "Asia", "India", "Tamil Nadu", "Chennai", "sports", "creator", 4340000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("techwithyesh", "Yeshwanth (Tech Content)", "Asia", "India", "Tamil Nadu", "Chennai", "science_&_technology", "creator", 386000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("olivia.anugraha", "Olivia Anugraha", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 312100, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("gukesh.official", "Gukesh", "Asia", "India", "Tamil Nadu", "Chennai", "sports", "creator", 1750000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("itznaga_raj", "Nagarajan", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 454000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("sanjkayy", "Sanjana AK", "Asia", "India", "Tamil Nadu", "Chennai", "fashion_&_style", "creator", 748100, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("_tejaswini_gowda_official", "Tejaswini Gowda", "Asia", "India", "Tamil Nadu", "Chennai", "fashion_&_style", "creator", 670900, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("teejayarunasalam", "TEEJAY", "Asia", "India", "Tamil Nadu", "Chennai", "music", "creator", 903300, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("manichandra_official", "Manichandra", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 608000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("dharshini_us7", "Dharshini Sambathkumar", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 469900, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("monisha.blessy", "Monisha Blessy B", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 1170000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("umariyazkhan", "Uma Riyaz", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 253300, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("actormunna_official", "Munna", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 191500, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("vinusha_devi", "Vinusha Devi", "Asia", "India", "Tamil Nadu", "Chennai", "fashion_&_style", "creator", 522900, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("dimplehayathi", "Dimple Hyati", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 1200000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("atlee47", "Atlee Kumar", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 2220000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("shivakumarr20", "Shiva Kumarr", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 166500, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("vsautos", "Vignesh Elangovan", "Asia", "India", "Tamil Nadu", "Chennai", "other_hobbies", "creator", 316300, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("capt_pradeepkrishnan", "Pradeep Krishnan", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 981600, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("prsoccerart", "Pradeep (Football Freestyler)", "Asia", "India", "Tamil Nadu", "Chennai", "sports", "creator", 114700, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("venkat_prabhu", "Venkat Prabhu", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 819000, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("thajmola", "Thaj", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 462600, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("kranthi_vlogger", "Kranthi Kumar Bonigala", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 66700, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("kathir_l", "Kathir", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 602600, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("satired", "Aravind (SA)", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 293300, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("raymondcallanan", "Raymond Callanan", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 82100, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("vjprem_", "VJ Prem", "Asia", "India", "Tamil Nadu", "Chennai", "film_tv_&_video", "creator", 184400, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
 R("dharmachandru", "Dharma Chandru", "Asia", "India", "Tamil Nadu", "Chennai", "diaries_&_daily_life", "creator", 63300, "2026-07", "socialveins.com Chennai influencer list (July 2026)"),
]

# bulk rows scraped from the public socialveins.com city lists (app/seed/creators_socialveins.txt)
# format: "## State|City|category|as_of" then "handle|Name|followers[|city]". Skips <10K followers, family/child accounts and duplicates.
CITY_STATE = {"Surat": "Gujarat", "Ernakulam": "Kerala", "Malappuram": "Kerala", "Coimbatore": "Tamil Nadu"}
def _num(t):
    t = t.strip().upper().replace(",", ""); m = 1
    if t.endswith("K"): m, t = 1000, t[:-1]
    elif t.endswith("M"): m, t = 1000000, t[:-1]
    return int(float(t) * m)
def bulk(path):
    seen = {r[0].lower() for r in ROWS}; out_rows = []; st = city = cat = asof = ""
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        if line.startswith("## "):
            st, city, cat, asof = line[3:].split("|"); continue
        if cat == "family": continue
        p = line.split("|"); h, name, fol = p[0].lower(), p[1], _num(p[2]); c = p[3] if len(p) > 3 else city
        if fol < 10000 or h in seen: continue
        seen.add(h); state = CITY_STATE.get(c, st)
        out_rows.append(R(h, name, "Asia", "India", state, c, cat, "athlete" if cat == "sports" and fol > 1000000 else "creator", fol, asof,
                          "socialveins.com %s influencer list (%s)" % (c, asof)))
    return out_rows
_bp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "seed", "creators_socialveins.txt")
if os.path.exists(_bp): ROWS += bulk(_bp)
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "seed", "influencer_directory.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(H); w.writerows(ROWS)
print(len(ROWS), "rows ->", out)
