# -*- coding: utf-8 -*-
"""
Bot Telegram -> site alexismindset.com (+ publication dans le canal Telegram d'Alexis).

Lancé automatiquement par GitHub Actions toutes les ~5 minutes (voir .github/workflows/bot.yml).
Il lit les messages reçus par le bot, range les images dans ce dépôt et met à jour data.json.
Le site lit ces fichiers directement : rien à republier.

PHOTOS (la 1re ligne de la légende = la commande) :
    cote2                      -> cote2.jpg      : Côte de 2 de l'accueil et de la page Côte de 2
    tpi melbet                 -> tpi-1.jpg      : coupon Total Pair/Impair Melbet
    tpi 1xbet                  -> tpi-2.jpg      : coupon Total Pair/Impair 1xBet
       (dans la même légende, on peut ajouter  code AB12C  et  cote 2.05)
    gagne  [texte libre]       -> ticket GAGNÉ ajouté à la page Résultats
    perdu  [texte libre]       -> ticket PERDU ajouté à la page Résultats
  Ajouter le mot  site   à la commande = ne PAS publier dans le canal (ex : "cote2 site").

MESSAGES TEXTE :
    code melbet AB12C 2.05     -> code + cote du Total P/I Melbet (même chose avec 1xbet)
    analyse                    -> analyse d'un match (voir le mode d'emploi, 1 info par ligne)
    statut gagne / statut perdu -> résultat de la dernière analyse
    annuler resultat           -> retire le dernier ticket ajouté
    annuler analyse            -> retire la dernière analyse ajoutée
    effacer tpi                -> vide les codes Total P/I
    aide                       -> rappelle la liste des commandes

Secrets GitHub (Settings > Secrets and variables > Actions) :
    TELEGRAM_BOT_TOKEN  : le jeton donné par @BotFather
    TELEGRAM_ALLOWED_ID : l'identifiant Telegram d'Alexis (plusieurs : séparés par des virgules)
    TELEGRAM_CHANNEL_ID : (facultatif) le canal, ex : @alexis_mindset — le bot doit en être ADMINISTRATEUR
"""
import datetime, json, os, re, sys, unicodedata, urllib.parse, urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED = {x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_ID", "").split(",") if x.strip()}
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFSET_FILE = os.path.join(ROOT, ".telegram_offset")
DATA_FILE = os.path.join(ROOT, "data.json")
SITE = "https://alexismindset.com"
CODE = "TIPG"
MAX_RESULTATS = 60
TZ = datetime.timezone(datetime.timedelta(hours=1))   # heure d'Afrique centrale/de l'Ouest (UTC+1)

LIENS = {"1xbet": "https://tinyurl.com/hn7v6cp3", "melbet": "https://tinyurl.com/5fjdnere"}
SEP = "━━━━━━━━━━━━━━━━━━━━"
PIED = f"\n{SEP}\n🎁 CODE PROMO À L'INSCRIPTION : {CODE}\n👉 {SITE}\n{SEP}\n⚠️ 18+ · Joue de manière responsable"

AIDE = """🤖 Commandes du bot Alexis Mindset

📸 PHOTO + légende :
• cote2 → Côte de 2 du jour
• tpi melbet  (ou tpi 1xbet) → coupon Total P/I
   ➕ tu peux ajouter dans la légende : code AB12C cote 2.05
• gagne → ticket gagné (page Résultats)
• perdu → ticket perdu (page Résultats)
Ajoute « site » (ex : cote2 site) pour ne pas publier dans le canal.

✍️ MESSAGE :
• code melbet AB12C 2.05 → code Total P/I
• analyse → analyse d'un match (1 info par ligne) :
   analyse
   Manchester City - PSG
   14/10 21:00 Ligue des champions
   prono: Les deux équipes marquent
   cote: 1.65
   code: AB12C 1xbet   (facultatif)
   Puis ton texte d'analyse…
• statut gagne / statut perdu → résultat de la dernière analyse
• annuler resultat / annuler analyse → retire le dernier ajout
• effacer tpi → vide les codes Total P/I

Le site se met à jour en 5 à 10 minutes."""


# ── outils ──
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()

def call(method, data=None, files=None):
    url = f"{API}/{method}"
    if files:
        boundary = "----alexisbot"
        body = b""
        for k, v in (data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (name, content) in files.items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                     f'Content-Type: image/jpeg\r\n\r\n').encode() + content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data or {}).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def reply(chat, text):
    try: call("sendMessage", {"chat_id": chat, "text": text})
    except Exception as e: print("reply:", e)

def download(file_id):
    info = call("getFile", {"file_id": file_id})
    with urllib.request.urlopen(f"{FILE_API}/{info['result']['file_path']}", timeout=60) as r:
        return r.read()

def save(rel, content):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f: f.write(content)

def load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as f: d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("tpi", {"melbet": {}, "1xbet": {}})
    d.setdefault("resultats", [])
    d.setdefault("analyses", [])
    return d

def save_data(d):
    d["maj"] = datetime.datetime.now(TZ).isoformat(timespec="minutes")
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=1)

def to_channel(photo, caption):
    if not CHANNEL: return
    try: call("sendPhoto", {"chat_id": CHANNEL, "caption": caption[:1024]}, {"photo": ("coupon.jpg", photo)})
    except Exception as e: print("canal:", e)

def code_cote(text):
    """Cherche « code XXX » et « cote 1.23 » dans un texte."""
    t = text.replace(",", ".")
    code = re.search(r"\bcode\s*:?\s*([A-Za-z0-9]{4,})", t, re.I)
    cote = re.search(r"\bcote\s*:?\s*(\d+(?:\.\d+)?)", t, re.I)
    return (code.group(1).upper() if code else ""), (cote.group(1) if cote else "")

def today():
    return datetime.datetime.now(TZ).date().isoformat()


# ── commandes ──
def on_photo(msg, d):
    chat = msg["chat"]["id"]
    caption = msg.get("caption", "") or ""
    lines = caption.splitlines() or [""]
    first = norm(lines[0]); rest = "\n".join(lines[1:]).strip()
    no_channel = bool(re.search(r"\bsite\b", first)); first = re.sub(r"\bsite\b", "", first).strip()
    fid = (msg.get("photo") or [{}])[-1].get("file_id") or (msg.get("document") or {}).get("file_id")
    if not fid:
        return reply(chat, "❌ Je n'ai pas trouvé d'image.")
    photo = download(fid)

    if re.fullmatch(r"(la )?cote ?(de )?2|c2", first):
        save("cote2.jpg", photo)
        if not no_channel:
            to_channel(photo, f"{SEP}\n⚽ CÔTE DE 2 DU JOUR\n{SEP}\n{rest + chr(10) if rest else ''}\n👉 {SITE}/cote-de-2.html\n🎯 1xBet : {LIENS['1xbet']}" + PIED)
        return reply(chat, "✅ Côte de 2 mise à jour sur le site" + ("" if no_channel or not CHANNEL else " et publiée dans le canal") + ".")

    m = re.fullmatch(r"(?:tpi|pair impair|total)\s*(melbet|1 ?x ?bet)", first)
    if m:
        bk = "melbet" if "melbet" in m.group(1) else "1xbet"
        save("tpi-1.jpg" if bk == "melbet" else "tpi-2.jpg", photo)
        code, cote = code_cote(caption)
        if code:
            d["tpi"][bk] = {"code": code, "cote": cote, "date": today()}
        if not no_channel:
            to_channel(photo, f"{SEP}\n🎲 TOTAL PAIR / IMPAIR — {bk.upper()}\n{SEP}\n"
                              + (f"🔑 Code coupon : {code}\n" if code else "") + (f"📈 Cote : {cote}\n" if cote else "")
                              + f"\n👉 {SITE}/total-pi.html\n🎯 {bk.upper()} : {LIENS[bk]}" + PIED)
        return reply(chat, f"✅ Coupon Total P/I {bk} mis à jour" + (f" (code {code}" + (f", cote {cote}" if cote else "") + ")" if code
                     else ".\nℹ️ Pense à envoyer le code : code " + bk + " AB12C 2.05"))

    if re.fullmatch(r"gagne|gagnee|win|won|perdu|perdue|lost|lose", first):
        won = first in ("gagne", "gagnee", "win", "won")
        stamp = datetime.datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
        rel = f"resultats/{stamp}-{msg.get('message_id', len(d['resultats']))}.jpg"
        save(rel, photo)
        d["resultats"].insert(0, {"f": rel, "statut": "won" if won else "lost",
                                  "date": datetime.datetime.now(TZ).strftime("%d/%m/%Y"), "txt": rest[:200]})
        del d["resultats"][MAX_RESULTATS:]
        if won and not no_channel:
            to_channel(photo, f"{SEP}\n🏆 TICKET GAGNANT\n{SEP}\n{rest + chr(10) if rest else ''}✅ Bravo à ceux qui ont suivi !\n👉 {SITE}/resultats.html" + PIED)
        return reply(chat, f"✅ Ticket {'gagné' if won else 'perdu'} ajouté à la page Résultats." + ("" if won else "\n👍 Publier aussi les tickets perdus rend le site crédible."))

    reply(chat, "❓ Je n'ai pas compris la légende de la photo.\n\n" + AIDE)


def on_text(msg, d):
    chat = msg["chat"]["id"]
    text = msg.get("text", "") or ""
    first = norm(text.splitlines()[0]) if text.strip() else ""

    if first in ("/start", "aide", "/aide", "help", "/help"):
        return reply(chat, AIDE)

    m = re.match(r"code (melbet|1 ?x ?bet)\s+([a-z0-9]{4,})(?:\s+(\d+(?:[.,]\d+)?))?", first)
    if m:
        bk = "melbet" if "melbet" in m.group(1) else "1xbet"
        code = m.group(2).upper(); cote = (m.group(3) or "").replace(",", ".")
        d["tpi"][bk] = {"code": code, "cote": cote, "date": today()}
        return reply(chat, f"✅ Code Total P/I {bk} : {code}" + (f" (cote {cote})" if cote else "") + " — visible sur le site d'ici quelques minutes.")

    if first == "effacer tpi":
        d["tpi"] = {"melbet": {}, "1xbet": {}}
        return reply(chat, "🧹 Codes Total P/I effacés.")

    if first in ("annuler resultat", "annuler resultats"):
        if d["resultats"]:
            r = d["resultats"].pop(0)
            return reply(chat, f"↩️ Dernier ticket retiré ({r['date']}).")
        return reply(chat, "Aucun ticket à retirer.")

    if first in ("annuler analyse", "annuler analyses"):
        if d["analyses"]:
            a = d["analyses"].pop(0)
            return reply(chat, f"↩️ Analyse retirée : {a['dom']} – {a['ext']}.")
        return reply(chat, "Aucune analyse à retirer.")

    if first == "analyse":
        lines = [l.strip() for l in text.splitlines()[1:] if l.strip()]
        if len(lines) < 2:
            return reply(chat, "❌ Analyse incomplète.\n\n" + AIDE)
        teams = re.split(r"\s+(?:-|–|vs|contre)\s+", lines[0], maxsplit=1, flags=re.I)
        if len(teams) != 2:
            return reply(chat, "❌ 2e ligne : écris les équipes comme ça → Manchester City - PSG")
        a = {"dom": teams[0].strip(), "ext": teams[1].strip(), "date": today(), "heure": "", "comp": "",
             "prono": "", "cote": "", "code": "", "bk": "", "analyse": "", "statut": ""}
        body = []
        for l in lines[1:]:
            n = norm(l)
            dm = re.match(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\s*(\d{1,2}[h:]\d{2})?\s*(.*)", l)
            if dm and not a["comp"] and not body and not n.startswith(("prono", "cote", "code")):
                y = dm.group(3) or str(datetime.date.today().year); y = ("20" + y) if len(y) == 2 else y
                a["date"] = f"{y}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}"
                a["heure"] = (dm.group(4) or "").replace("h", ":"); a["comp"] = dm.group(5).strip()
            elif n.startswith("prono"):  a["prono"] = l.split(":", 1)[-1].strip() if ":" in l else l[5:].strip()
            elif n.startswith("cote"):   a["cote"] = re.sub(r"[^\d.,]", "", l).replace(",", ".")
            elif n.startswith("code"):
                parts = (l.split(":", 1)[-1] if ":" in l else l[4:]).split()
                if parts: a["code"] = parts[0].upper()
                if len(parts) > 1: a["bk"] = parts[1]
            else: body.append(l)
        a["analyse"] = "\n".join(body)
        if not a["prono"]:
            return reply(chat, "❌ Il manque la ligne  prono: …")
        d["analyses"].insert(0, a)
        del d["analyses"][40:]
        return reply(chat, f"✅ Analyse ajoutée : {a['dom']} – {a['ext']} ({a['prono']}" + (f" @ {a['cote']}" if a["cote"] else "") + ").\nElle apparaîtra sur la page Pronostics d'ici quelques minutes.")

    if first.startswith("statut "):
        # statut gagne / statut perdu → résultat de la dernière analyse
        st = "won" if "gagn" in first else "lost" if "perdu" in first else ""
        if d["analyses"] and st:
            d["analyses"][0]["statut"] = st
            return reply(chat, f"✅ Dernière analyse marquée {'gagnée' if st == 'won' else 'perdue'}.")
        return reply(chat, "Écris : statut gagne  ou  statut perdu")

    reply(chat, "❓ Commande inconnue.\n\n" + AIDE)


def main():
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN manquant")
    offset = 0
    if os.path.exists(OFFSET_FILE):
        try: offset = int(open(OFFSET_FILE).read().strip() or 0)
        except ValueError: offset = 0
    updates = call("getUpdates", {"offset": offset, "timeout": 0}).get("result", [])
    if not updates:
        print("Aucun nouveau message."); return
    d = load_data()
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message")
        if not msg: continue
        sender = str(msg.get("from", {}).get("id", ""))
        if not ALLOWED:   # pas encore configuré : on n'obéit à personne, on donne juste l'identifiant
            reply(msg["chat"]["id"], f"🔧 Bot pas encore configuré.\nTon identifiant Telegram : {sender}\n→ à mettre dans le secret TELEGRAM_ALLOWED_ID sur GitHub.")
            continue
        if sender not in ALLOWED:
            reply(msg["chat"]["id"], "⛔ Ce bot est privé.")
            continue
        try:
            if msg.get("photo") or (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
                on_photo(msg, d)
            elif msg.get("text"):
                on_text(msg, d)
        except Exception as e:
            print("erreur:", e)
            reply(msg["chat"]["id"], f"⚠️ Erreur : {e}")
    save_data(d)
    with open(OFFSET_FILE, "w") as f: f.write(str(offset))
    print(f"{len(updates)} message(s) traité(s).")


if __name__ == "__main__":
    main()
