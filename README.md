# FoodCal

เว็บสำหรับอัปโหลด/ถ่ายภาพอาหาร ใช้โมเดลที่ train แล้วจำแนกอาหาร แสดงแคลอรีและสารอาหารโดยประมาณ และบันทึกประวัติแยกตามบัญชีผู้ใช้

## สารบัญ

- [โครงสร้างโปรเจกต์](#โครงสร้างโปรเจกต์)
- [สิ่งที่ต้องติดตั้ง](#สิ่งที่ต้องติดตั้ง)
- [ติดตั้งและรันในเครื่อง](#ติดตั้งและรันในเครื่อง)
- [วิธีใช้งานเว็บไซต์](#วิธีใช้งานเว็บไซต์)
- [ใส่โมเดลที่ train แล้ว](#ใส่โมเดลที่-train-แล้ว)
- [แก้ปัญหาเบื้องต้น](#แก้ปัญหาเบื้องต้น)

## โครงสร้างโปรเจกต์

- `frontend/` — หน้าเว็บ HTML, CSS, JavaScript
- `backend/` — FastAPI, ระบบ login/JWT, ฐานข้อมูล และ model inference
- `backend/model/` — ONNX models สำหรับ Food-101 และ THFOOD-50 พร้อมรายชื่อคลาสและข้อมูลโภชนาการ
- `database/` — ข้อมูลโภชนาการเริ่มต้น
- `data/foodcal.db` — SQLite ที่สร้างอัตโนมัติเมื่อรัน backend ในเครื่อง; มีบัญชีผู้ใช้และประวัติมื้อ จึงไม่ควร commit/share ไฟล์นี้

## สิ่งที่ต้องติดตั้ง

สำหรับทดลองในเครื่อง:

1. **Python 3.11 หรือ 3.12** — ใช้รัน backend และ frontend แบบ static
2. **Git** — ใช้ clone repository (ถ้ามีโฟลเดอร์โปรเจกต์อยู่แล้วไม่ต้องติดตั้งเพิ่ม)
3. **ไม่ต้องติดตั้ง Node.js, npm หรือ Docker** เพื่อรันเว็บในเครื่อง
4. **โมเดล FoodCal** — ONNX Runtime ติดตั้งจาก `backend/requirements.txt`; ต้องมีไฟล์ ONNX และรายชื่อคลาสของโมเดลที่ต้องการใช้ โดย Food-101 มี sidecar เพิ่มอีกหนึ่งไฟล์

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

ONNX Runtime จะติดตั้งพร้อม dependencies จาก `backend/requirements.txt` ทั้ง local และ Docker

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
python -m uvicorn ba<http://localhost:8000/health>ckend.app:app --reload --host 127.0.0.1 --port 8000
```

เมื่อเห็นข้อความว่า Uvicorn กำลังรับคำขอ ให้เปิดใช้งาน backend ได้แล้ว:

- ตรวจสถานะ: 
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

3. เมื่อ login แล้ว เลือกชุดโมเดลให้ตรงกับอาหารในภาพ: **Food-101** สำหรับ 101 คลาสสากล หรือ **THFOOD-50** สำหรับ 50 คลาสอาหารไทย
4. เลือก **เลือกรูปภาพ** หรือ **ถ่ายรูป**; บนมือถือปุ่มถ่ายรูปจะเปิดกล้อง ระบุปริมาณโดยประมาณเป็นกรัม แล้วกด **วิเคราะห์จานนี้**
5. ดูชื่ออาหาร ความมั่นใจ แคลอรีและสารอาหารโดยประมาณ
6. กด **บันทึกมื้อนี้** เพื่อเก็บประวัติของบัญชีนั้น
7. บัญชีเดโมทั้งสามมีประวัติแยกกัน; admin สร้างบัญชี user เพิ่มได้จากฟอร์ม **สร้างบัญชีผู้ใช้**

ข้อมูลบัญชีและมื้อ local เก็บใน `data/foodcal.db`; รหัสผ่านเก็บเป็น Argon2 hash ไม่ใช่ plain text. บัญชีทดลองเป็นข้อมูลสาธิต อย่าใช้รหัสผ่านเดียวกันกับบัญชีส่วนตัวหรือใช้บน production

## โมเดลจำแนกภาพ

เว็บให้เลือกใช้โมเดล Food-101 (101 คลาส) หรือ THFOOD-50 (50 คลาส) ก่อนวิเคราะห์. Food-101 ใช้ `food101_effnetb0.onnx`, `food101_effnetb0.onnx.data` และ `classes.json`; THFOOD-50 ใช้ `thfood50_effnetb0.onnx` และ `classes_thfood50.json` โดยไฟล์ ONNX ของ THFOOD-50 ที่ส่งออกมามีน้ำหนักอยู่ในไฟล์เดียว. รายชื่อคลาสต้องเรียงตรงกับ output ของโมเดล. ทั้งสองโมเดลใช้ preprocessing แบบ resize ด้านสั้นเป็น 256, center crop 224 และ ImageNet normalization. โมเดลจำแนกชื่ออาหารจากภาพ ไม่ได้คำนวณน้ำหนักจริงหรือสารอาหารจากภาพ

คะแนน softmax ของ Food-101 และ THFOOD-50 มาจากคนละโมเดล จึงไม่ควรนำมาเทียบกันโดยตรง. ข้อมูลโภชนาการในเว็บมีแหล่ง USDA สำหรับคลาส Food-101; ฝั่ง THFOOD-50 จะแสดงโภชนาการเฉพาะคลาสที่มีรายการจับคู่ในฐานข้อมูลเท่านั้น (ปัจจุบันมี Pad Thai) และจะไม่เดาค่าให้คลาสอื่น

`backend/model/usda_fndds_mappings.json` เก็บ snapshot จาก USDA FoodData Central FNDDS 2021–2023 และ SR Legacy ที่จับคู่กับคลาสโมเดล พร้อม FDC ID และชื่อรายการต้นทาง. เว็บใช้ข้อมูลจากไฟล์นี้โดยตรง ไม่เรียก API ของ USDA ทุกครั้งที่ทำนาย และไม่ต้องใช้ API key. ปัจจุบันมี 43 คลาสที่จับคู่ตรง, 45 คลาสใช้รายการใกล้เคียง, และ 13 คลาสยังใช้ค่าแคลอรี่ชั่วคราวจาก `calories.json` โดยไม่มีสารอาหารหลักหรือแหล่ง USDA. ระบบแสดงสถานะและลิงก์รายการ USDA ต้นทางสำหรับค่าที่จับคู่แล้ว; ค่าใกล้เคียงและค่าชั่วคราวไม่ควรอธิบายว่าเป็นโภชนาการสูตรตรงของอาหารในภาพ. อ้างอิง: U.S. Department of Agriculture, Agricultural Research Service, FoodData Central, FNDDS 2021–2023 และ SR Legacy, https://fdc.nal.usda.gov/.

## แก้ปัญหาเบื้องต้น

- **หน้าเว็บไม่ขึ้น / connection refused ที่ 8080:** ตรวจว่า Terminal frontend ยังรันอยู่. ถ้าหยุดด้วย `Ctrl+C` ให้รันคำสั่ง `python3 -m http.server 8080 --directory frontend --bind 127.0.0.1` ใหม่
- **เว็บขึ้นแต่ login/API ไม่ได้:** ตรวจว่า backend Terminal ยังรันและเปิด <http://localhost:8000/health> ได้
- **`Address already in use`:** มีโปรแกรมใช้งาน port `8080` หรือ `8000`; หยุด process เดิมก่อน หรือแก้ port แล้วปรับ `frontend/config.js` ให้ API URL ตรงกัน
- **`ModuleNotFoundError`:** ตรวจว่า `.venv` active แล้วติดตั้ง `python -m pip install -r backend/requirements.txt`
- **login ไม่สำเร็จหลังเริ่ม backend:** ตรวจว่า Terminal backend ตั้ง `DEMO_LOGIN_ENABLED=true` และเริ่ม backend ใหม่หลังตั้ง environment variables
- **วิเคราะห์แล้วแจ้งไม่มี model:** ตรวจว่า ONNX และ class list ของโมเดลที่เลือกอยู่ใน `backend/model/` แล้ว restart API; sidecar `.onnx.data` จำเป็นเฉพาะ Food-101
- **แคลอรี/สารอาหารไม่พบ:** ตรวจว่าคลาสที่โมเดลทำนายมีรายการตรงกันใน `database/foods_seed.json`; ค่า seed เป็นข้อมูลตัวอย่าง ควรตรวจสอบก่อนใช้จริง
- **Browser แจ้ง CORS:** ใช้ local frontend ที่ `http://localhost:8080` กับ backend ที่ `http://localhost:8000`
