---
title: FoodCal API
emoji: 🍽️
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
---

# FoodCal

เว็บสำหรับอัปโหลด/ถ่ายภาพอาหาร ใช้โมเดลที่ train แล้วจำแนกอาหาร แสดงแคลอรีและสารอาหารโดยประมาณ และบันทึกประวัติแยกตามบัญชีผู้ใช้

## สารบัญ

- [โครงสร้างโปรเจกต์](#โครงสร้างโปรเจกต์)
- [สิ่งที่ต้องติดตั้ง](#สิ่งที่ต้องติดตั้ง)
- [ติดตั้งและรันในเครื่อง](#ติดตั้งและรันในเครื่อง)
- [วิธีใช้งานเว็บไซต์](#วิธีใช้งานเว็บไซต์)
- [ใส่โมเดลที่ train แล้ว](#ใส่โมเดลที่-train-แล้ว)
- [แก้ปัญหาเบื้องต้น](#แก้ปัญหาเบื้องต้น)
- [Deploy](#deploy)

## โครงสร้างโปรเจกต์

- `frontend/` — หน้าเว็บ HTML, CSS, JavaScript
- `backend/` — FastAPI, ระบบ login/JWT, ฐานข้อมูล และ model inference
- `backend/model/` — ที่วางโมเดล `foodcal.pt` และรายชื่อคลาส `classes.json`
- `database/` — ข้อมูลโภชนาการเริ่มต้น
- `data/foodcal.db` — SQLite ที่สร้างอัตโนมัติเมื่อรัน backend ในเครื่อง; มีบัญชีผู้ใช้และประวัติมื้อ จึงไม่ควร commit/share ไฟล์นี้
- `deploy/DEPLOY.md` — คู่มือ deploy Vercel + Hugging Face Spaces + Neon
- `Dockerfile` — ใช้สำหรับ deploy backend บน Hugging Face Spaces เท่านั้น

## สิ่งที่ต้องติดตั้ง

สำหรับทดลองในเครื่อง:

1. **Python 3.11 หรือ 3.12** — ใช้รัน backend และ frontend แบบ static
2. **Git** — ใช้ clone repository (ถ้ามีโฟลเดอร์โปรเจกต์อยู่แล้วไม่ต้องติดตั้งเพิ่ม)
3. **ไม่ต้องติดตั้ง Node.js, npm หรือ Docker** เพื่อรันเว็บในเครื่อง
4. **PyTorch** — ใช้ทำนายภาพ ต้องติดตั้งแยกตาม OS ตามขั้นตอนด้านล่าง
5. **โมเดล FoodCal จริง** — ยังไม่จำเป็นสำหรับเปิดเว็บ/login แต่ต้องมีจึงจะวิเคราะห์ภาพได้

## ติดตั้งและรันในเครื่อง

ทำตามนี้จาก Terminal ที่โฟลเดอร์หลักของ FoodCal (ตำแหน่งที่มี `README.md`). ให้เปิด **Terminal แรกสำหรับ backend** และ **Terminal ที่สองสำหรับ frontend**; ต้องปล่อยทั้งสอง Terminal ทำงานไว้ขณะใช้เว็บ.

### 1. สร้าง Python virtual environment

**macOS / Linux:**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

ถ้า Windows ปฏิเสธการ activate script ให้เปิด Command Prompt แล้วใช้ `.venv\Scripts\activate.bat` หรือเปลี่ยน execution policy ตามนโยบายเครื่อง

### 2. ติดตั้ง Backend dependencies

รันใน Terminal แรก หลัง activate `.venv` แล้ว:

```sh
python -m pip install -r backend/requirements.txt
```

ติดตั้ง PyTorch เพิ่ม:

- **macOS หรือ Windows:** `python -m pip install torch`
- **Linux ที่ใช้ CPU:** `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`

> ใน Docker image สำหรับ Hugging Face จะติดตั้ง CPU-only PyTorch ให้อัตโนมัติ ส่วนขั้นตอนด้านบนเป็นการติดตั้งสำหรับรันในเครื่อง

### 3. ตั้งค่าบัญชีทดลองสำหรับ local

บัญชีทดลองเปิดเฉพาะตอนพัฒนาในเครื่อง ห้ามเปิดเมื่อนำ backend ขึ้น public internet

**macOS / Linux (Terminal แรก):**

```sh
export JWT_SECRET="$(openssl rand -hex 32)"
export DEMO_LOGIN_ENABLED=true
```

**Windows PowerShell (Terminal แรก):**

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:JWT_SECRET = -join ($bytes | ForEach-Object { $_.ToString("x2") })
$env:DEMO_LOGIN_ENABLED = "true"
```

เก็บ Terminal แรกนี้ไว้และใช้ Terminal เดิมเริ่ม backend ในขั้นถัดไป เพื่อให้ตัวแปรยังอยู่

### 4. เริ่ม Backend API

จากโฟลเดอร์หลัก รันใน Terminal แรก:

```sh
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

เมื่อเห็นข้อความว่า Uvicorn กำลังรับคำขอ ให้เปิดใช้งาน backend ได้แล้ว:

- ตรวจสถานะ: <http://localhost:8000/health>
- API documentation: <http://localhost:8000/docs>

ฐานข้อมูล local ที่ `data/foodcal.db` และตาราง `users`, `foods`, `meals` จะถูกสร้างอัตโนมัติเมื่อ backend เริ่มทำงานครั้งแรก

### 5. เริ่ม Frontend

เปิด **Terminal ที่สอง** แล้ว `cd` ไปยังโฟลเดอร์หลักของ FoodCal ก่อน รัน:

**macOS / Linux:**

```sh
python3 -m http.server 8080 --directory frontend --bind 127.0.0.1
```

**Windows PowerShell:**

```powershell
python -m http.server 8080 --directory frontend --bind 127.0.0.1
```

เปิดเว็บที่ <http://localhost:8080>. ต้องปล่อย Terminal ทั้งสองอันทำงานไว้พร้อมกัน: Terminal แรกคือ API ที่ port `8000`, Terminal ที่สองคือหน้าเว็บที่ port `8080`.

### 6. วิธีหยุดและเปิดใหม่

- กด `Ctrl+C` ใน Terminal ของ frontend เพื่อหยุดหน้าเว็บ
- กด `Ctrl+C` ใน Terminal ของ backend เพื่อหยุด API
- เมื่อต้องการเปิดใหม่ ให้ activate `.venv` และตั้ง `JWT_SECRET`/`DEMO_LOGIN_ENABLED` ใน Terminal backend อีกครั้ง แล้วเริ่มสองคำสั่งตามขั้นตอน 4–5
- การ refresh หน้าเว็บทำได้ตามปกติ; token login อยู่ใน session ของแท็บและมีอายุ 12 ชั่วโมง ปิดแท็บหรือหมดอายุแล้วให้ login ใหม่

## วิธีใช้งานเว็บไซต์

1. เปิด <http://localhost:8080>
2. เลือกปุ่ม **เข้าใช้** ของบัญชีเดโมที่หน้า login หรือกรอกบัญชีเอง:

   | Email | Password |
   | --- | --- |
   | `demo1@foodcal.test` | `FoodCalDemo1!` |
   | `demo2@foodcal.test` | `FoodCalDemo2!` |
   | `demo3@foodcal.test` | `FoodCalDemo3!` |

3. เมื่อ login แล้ว เลือก **เลือกรูปภาพ** หรือ **ถ่ายรูป**; บนมือถือปุ่มถ่ายรูปจะเปิดกล้อง
4. ระบุปริมาณโดยประมาณเป็นกรัม แล้วกด **วิเคราะห์จานนี้**
5. ดูชื่ออาหาร ความมั่นใจ แคลอรีและสารอาหารโดยประมาณ
6. กด **บันทึกมื้อนี้** เพื่อเก็บประวัติของบัญชีนั้น
7. บัญชีเดโมทั้งสามมีประวัติแยกกัน; admin สร้างบัญชี user เพิ่มได้จากฟอร์ม **สร้างบัญชีผู้ใช้**

ข้อมูลบัญชีและมื้อ local เก็บใน `data/foodcal.db`; รหัสผ่านเก็บเป็น Argon2 hash ไม่ใช่ plain text. บัญชีทดลองเป็นข้อมูลสาธิต อย่าใช้รหัสผ่านเดียวกันกับบัญชีส่วนตัวหรือใช้บน production

## ใส่โมเดลที่ train แล้ว

วางไฟล์ไว้ดังนี้:

- `backend/model/foodcal.pt` — TorchScript model ที่โหลดด้วย `torch.jit.load()` ได้
- `backend/model/classes.json` — JSON array ของชื่อคลาส เรียงตามลำดับ output ของโมเดล

ตรวจให้ preprocessing ใน `backend/inference.py` (ขนาดภาพ, resize, normalization) ตรงกับขั้นตอน train และชื่อคลาสตรงกับ `food_key` ใน `database/foods_seed.json`. หลังวางโมเดล ให้ restart backend. ไฟล์ `classes.json` ที่แนบใน repo เป็นเพียงตัวอย่าง และไม่มี trained weights.

หากไม่มีไฟล์โมเดล เว็บและ login ยังเปิดได้ แต่ `/api/predict` จะตอบว่า model ยังไม่พร้อม; จะไม่มีผลทำนายปลอม. ระบบจำแนกชื่ออาหารจากภาพแล้วคูณข้อมูลโภชนาการตามน้ำหนักที่ผู้ใช้กรอก ไม่ได้คำนวณน้ำหนักจริงจากภาพ

## แก้ปัญหาเบื้องต้น

- **หน้าเว็บไม่ขึ้น / connection refused ที่ 8080:** ตรวจว่า Terminal frontend ยังรันอยู่. ถ้าหยุดด้วย `Ctrl+C` ให้รันคำสั่ง `python3 -m http.server 8080 --directory frontend --bind 127.0.0.1` ใหม่
- **เว็บขึ้นแต่ login/API ไม่ได้:** ตรวจว่า backend Terminal ยังรันและเปิด <http://localhost:8000/health> ได้
- **`Address already in use`:** มีโปรแกรมใช้งาน port `8080` หรือ `8000`; หยุด process เดิมก่อน หรือแก้ port แล้วปรับ `frontend/config.js` ให้ API URL ตรงกัน
- **`ModuleNotFoundError`:** ตรวจว่า `.venv` active แล้วติดตั้ง `python -m pip install -r backend/requirements.txt`; ถ้าข้อความพูดถึง `torch` ให้ติดตั้ง PyTorch ตาม OS ด้านบน
- **login ไม่สำเร็จหลังเริ่ม backend:** ตรวจว่า Terminal backend ตั้ง `DEMO_LOGIN_ENABLED=true` และเริ่ม backend ใหม่หลังตั้ง environment variables
- **วิเคราะห์แล้วแจ้งไม่มี model:** วาง TorchScript ไฟล์ชื่อ `foodcal.pt` ใน `backend/model/` และ restart API
- **แคลอรี/สารอาหารไม่พบ:** ตรวจว่าคลาสที่โมเดลทำนายมีรายการตรงกันใน `database/foods_seed.json`; ค่า seed เป็นข้อมูลตัวอย่าง ควรตรวจสอบก่อนใช้จริง
- **Browser แจ้ง CORS:** ใช้ local frontend ที่ `http://localhost:8080` กับ backend ที่ `http://localhost:8000`; ใน production ต้องตั้ง `CORS_ORIGINS` ให้ตรงกับ domain ของเว็บ

## Deploy

Vercel ใช้เสิร์ฟ frontend เท่านั้น; FastAPI/PyTorch อยู่บน Hugging Face Spaces และ production database ใช้ Neon Postgres เพื่อให้ข้อมูลบัญชี/ประวัติไม่หายเมื่อ container restart. ขั้นตอนทั้งหมดและ environment variables อยู่ใน [deploy/DEPLOY.md](deploy/DEPLOY.md). อย่าเปิด `DEMO_LOGIN_ENABLED` ใน public backend.
