# Electronics Department - Equipment Management System
University Institute of Computing, Chandigarh University

ESP8266 + MFRC522 + OLED reader -> FastAPI server (MySQL) -> React web app, now **live on the internet**,
with **student self-registration by QR code** and **several laboratories in one system**.

```
firmware/lab_rfid_node/   Arduino sketch for the NodeMCU reader (hardware is unchanged)
backend/                  FastAPI + SQLAlchemy + MySQL
frontend/                 React web app (frontend/dist is the ready-built website)
render.yaml               one-click setup for the free Render host
```

## What is new in this version
| Feature | How it works |
|---|---|
| Live website | One free Render service serves the website and the API. Database on TiDB Cloud (free). |
| QR registration | Each lab has a QR code. The student opens a form on his phone, submits, and the request appears on the teacher's **Registrations** page. The teacher taps the student's ID card on the reader and approves. |
| Stock by every staff role | Administrator, teacher and lab assistant can all add and edit stock. **Change history** records who changed what, the old and new numbers and the reason. |
| Several labs | Every item, loan, reader and QR code belongs to a lab. Staff see only the labs assigned to them; the administrator sees all and switches lab in the sidebar. Students register once and can borrow in any lab (they must tap their card at **that** lab's reader). |
| Reader security | Every reader has its own ID and key, tied to one lab. Keys are stored only as hashes and can be renewed. |
| E-mail | Sent through the Gmail API over HTTPS (free cloud hosts block normal SMTP). Switching to the teacher's Gmail needs only new environment variables. |

## 1. Upgrading the system you already have (no data loss)
1. Stop the backend. Extract this zip over your project folder (your `venv`, `node_modules` and `.env` are not in the zip).
2. `cd backend`, `pip install -r requirements.txt`, then start as before (`uvicorn app.main:app --host 0.0.0.0 --port 8000`).
3. On the first start the system upgrades the database by itself: it creates the first laboratory, moves **all existing stock, loans and scans into it**, assigns your existing teachers and assistants to it, and keeps your reader working (the old `DEVICE_KEY` becomes the key of reader `LAB-RFID-01`). Nothing is deleted.
4. Rebuild the website only if you change the code (`cd frontend && npm install && npm run build`).
5. The reader sketch needs re-uploading only when you move to the live server (see step 6).

## 2. Put the project on GitHub
Create a GitHub account and a **private** repository, then upload the whole project folder. Keep the folder `frontend/dist` (it is the built website, so Render does not need Node). Never upload `.env`.

## 3. Database: TiDB Cloud (free)
1. Sign up at tidbcloud.com and create a free **Starter** cluster (region nearest to you).
2. Open **Connect**, choose a general/"Python (PyMySQL)" connection, and note host, port (4000), user and password. Create a database called `lab_db` (or use the default one).
3. Your `DATABASE_URL` is: `mysql+pymysql://USER:PASSWORD@HOST:4000/lab_db`  (if the password has symbols such as `@` or `#`, write them URL-encoded, e.g. `@` = `%40`). Set `DB_SSL=true`.

## 4. Gmail sending (your Gmail now, the teacher's later)
Do this once. It gives the system permission to **send** mail from one Gmail account. It cannot read the mailbox.
1. Open console.cloud.google.com, create a project, then **APIs and Services > Library** and enable **Gmail API**.
2. **OAuth consent screen**: user type External, app name e.g. "Lab System", your e-mail as support and developer contact. Add the scope `.../auth/gmail.send`. Add the Gmail account that will send as a **test user**. Then press **Publish app** (status "In production"). Without this, Google expires the permission after 7 days. You may see an "unverified app" warning; for your own use this is fine.
3. **Credentials > Create credentials > OAuth client ID**, type **Desktop app**. Copy the client ID and secret.
4. On your PC, in the `backend` folder: `python tools/get_gmail_token.py CLIENT_ID CLIENT_SECRET`. A browser opens: sign in with the Gmail account that should send, allow. The script prints `GMAIL_REFRESH_TOKEN` and `GMAIL_SENDER`.
5. **To switch to the teacher's Gmail later:** run step 4 again while signed in as the teacher (add the teacher as a test user first), then change only `GMAIL_REFRESH_TOKEN` and `GMAIL_SENDER` on the server and restart.

A normal Gmail account can send about 500 e-mails a day (check Google's current limit). Each issue sends two e-mails (code and receipt).

## 5. Render (free host)
1. Sign up at render.com with GitHub. **New > Blueprint**, pick your repository. Render reads `render.yaml`.
2. Fill the environment variables it asks for:
   - `DATABASE_URL` from step 3, `DB_SSL` is already true
   - `ADMIN_PASSWORD` your own first admin password (the server refuses to start with the example one)
   - `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER` from step 4
   - `PUBLIC_URL` the address Render gives you, e.g. `https://electronics-lab.onrender.com` (add it after the first deploy)
   - `SECRET_KEY`, `DEVICE_KEY`, `CRON_TOKEN` are generated for you (copy `CRON_TOKEN` for step 7)
3. Deploy. Open the address, sign in as `admin` with your `ADMIN_PASSWORD`, and set a new password. Open **Settings > Send test email** to check the Gmail link.

## 6. Reader (hardware unchanged)
1. In the web app open **Labs and readers**. Your first reader `LAB-RFID-01` exists already; press **New key** to get a key you can copy (shown once).
2. In `lab_rfid_node.ino` set `WIFI_SSID`, `WIFI_PASS`, `SERVER_URL = "https://YOUR-APP.onrender.com/api/rfid/scan"`, `DEVICE_ID` and `DEVICE_KEY` (the key you copied), then upload.
3. The reader must reach the internet. College Wi-Fi that asks for a login page will not work; use a hotspot or ask IT for a plain 2.4 GHz network.
4. Watch the Serial Monitor (115200) the first time: it prints the free memory at start. The HTTPS link encrypts the traffic but does not verify the server's certificate (`setInsecure()`); that is acceptable for a pilot, and pinning a certificate is a later improvement.

## 7. Reminders on a sleeping free server
Render's free service sleeps after about 15 minutes without visitors. The reader asks for screens every 3 seconds, so while it is powered the server stays awake. To make sure the daily reminders still go out, add a free job at cron-job.org that opens
`https://YOUR-APP.onrender.com/api/cron/reminders?token=YOUR_CRON_TOKEN` once a day.

## 8. QR registration
**Labs and readers > Registration QR** shows the QR code and link for a lab. Print it (Print button) and put it on the lab door or counter. A student scans it with the phone camera, fills the form and submits. Staff open **Registrations** (a red number in the menu shows how many are waiting), check the details, press **Start scan**, let the student tap the ID card, and press **Approve and register**. They can also send it back with a note or reject it; the student is told by e-mail each time.
Protection: no login is needed to submit, so the form allows only 5 attempts per address per 10 minutes, has a hidden trap field for bots, requires consent, and nothing becomes a student until staff approve.

## 9. Adding a second laboratory
1. **Labs and readers > Add laboratory** (name and short code).
2. Add its reader (**Add reader**, choose the lab), copy the key into that reader's sketch.
3. **Staff**: tick the labs each teacher or assistant may work in.
4. Add its stock inside that lab (switch lab in the sidebar). Print its own QR code.
A teacher of one lab cannot see or change another lab's stock, loans, scans or registrations.

## 10. What to expect on free plans (please check the providers' current terms)
- Render free: sleeps when idle; the first request after sleeping can take 30 to 60 seconds. Free services also cannot send SMTP e-mail, which is why Gmail API is used.
- TiDB Cloud Starter: free monthly allowance of storage and request units; the reader's 3-second polling is answered from memory most of the time to save it.
- This setup is fine for a demo and a small lab. For daily use by many students, a paid Render plan removes the sleeping.
- Only one server process is supported (the "waiting for card" state is kept in memory).

## Rules implemented (unchanged)
30-day loan, one 30-day renewal, fine per unit per day (all in Settings). Issue needs the student's own card scan on that lab's reader and one e-mailed code for the whole item list. OLED screens and receipt e-mails for every issue and return. Daily reminder e-mail listing all pending items.

## Tests that were run
Automated end-to-end tests (SQLite and MySQL/MariaDB): issue, return, fines, codes, receipts, reminders, labs, per-reader keys, QR registration with approval, rate limit, teacher stock edits and history, upgrade of an old database, production-safety checks, Gmail API request format (with a simulated Google). A real browser test covered the phone form, approval by card scan, labs, QR image, reader key and lab switcher. **Not tested here:** real Gmail delivery, TiDB Cloud itself, Render itself, and the new HTTPS firmware on the physical reader.
