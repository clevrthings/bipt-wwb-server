# BIPT → Shure Wireless Workbench Inclusion Lists

Deze applicatie genereert automatisch **Shure Wireless Workbench inclusion lists (`.ils`)**
op basis van de **officiële BIPT-zonedocumenten** voor draadloze microfoons in België.

De app is ontworpen om:
- continu up-to-date te blijven,
- eenvoudig te gebruiken te zijn voor audio professionals,
- en stabiel te draaien op een **Synology NAS via Docker**.

---

## ✨ Features

- 📥 Automatische download van BIPT zone-PDF’s
- 🧠 Slimme detectie van nieuwe kwartalen
- 🗂️ Generatie van Shure WWB `.ils` inclusion lists
- 🟢 Per provincie: **alle bruikbare frequenties** (vergund + vrijgesteld)
- 🟣 Eén globale lijst **“Vrije frequenties”**
- 🕒 Houdt **huidig + volgend kwartaal** beschikbaar
- 🗑️ Verwijdert automatisch verouderde kwartaalbestanden
- 🌐 Simpele webpagina om bestanden te downloaden
- 📊 Debug/admin pagina met bezoekers- en downloadstatistieken
- 🔐 Adminpagina beveiligd via environment variables
- 🐳 Klaar voor Docker & Synology Container Manager

---

## 🌍 Webinterface

### Publieke pagina
- Toont beschikbare `.ils` bestanden
- Bevat een korte handleiding voor import in WWB
- Link naar officiële Shure Wireless Workbench download

### Debug / admin pagina
- URL: `/debug`
- Beveiligd met Basic Auth
- Toont statistieken en status
- Laat manueel een update-check uitvoeren

---

## 📘 Importeren in Shure Wireless Workbench

1. Open **Frequency Coordination**
2. Klik rechts onderaan op **Spectrum**
3. Klik op het **⚙️ gear-icoon**
4. Bij **User Groups**:
   - vink **“Account for user groups when calculating frequencies”** aan
5. Klik rechts naast **List** op **Manage**
6. Kies **Custom**
7. Klik op het **⚙️ gear-icoon**
8. Kies **Import Groups**
9. Selecteer het gedownloade `.ils` bestand
10. Klik op **Save**

De inclusion groups verschijnen daarna onder **Custom inclusion lists**.

---

## 🧪 Lokaal testen (zonder Docker)

```bash
git clone https://github.com/<jouw-username>/bipt-wwb-server.git
cd bipt-wwb-server

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATA_DIR=./data
export DEBUG_USER=admin
export DEBUG_PASS=test123
export TZ=Europe/Brussels

uvicorn app.main:app --reload --port 8080
```

---

## 🐳 Docker / Synology NAS

```bash
git clone https://github.com/<jouw-username>/bipt-wwb-server.git
cd bipt-wwb-server
cp .env.example .env
docker compose up -d --build
```

---

## ⚙️ Environment variables

Zie `.env.example` voor alle opties.

---

## 🔐 Security

- Adminpagina is niet publiek
- Credentials via environment variables
- Gebruik sterke wachtwoorden of IP-beperkingen

---

## 📜 Licentie

MIT License

---

## 🧭 Disclaimer

Deze tool vervangt geen officiële BIPT-vergunningen.
De gebruiker blijft verantwoordelijk voor correct en legaal frequentiegebruik.
