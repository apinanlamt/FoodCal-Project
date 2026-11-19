# FoodCal: Deploy Frontend ด้วย Vercel

## โครงสร้าง deploy ที่ใช้

- **Vercel:** เสิร์ฟเว็บไซต์ static จาก `frontend/`
- **Hugging Face Spaces (Docker):** รัน FastAPI และโมเดล PyTorch บน CPU
- **Neon Postgres:** เก็บบัญชีและประวัติมื้อถาวร

Vercel เหมาะกับ frontend แต่ไม่ใช้เก็บ SQLite และ image-classification backend นี้ต้องโหลด PyTorch/model ซึ่งไม่เหมาะจะ bundle เป็น Vercel Function. Backend ใช้ Neon แทน SQLite ตอน deploy เพื่อไม่ให้ข้อมูลหายเมื่อ container restart. บริการฟรีอาจ sleep/จำกัดโควตา ควรตรวจข้อกำหนดปัจจุบันของแต่ละผู้ให้บริการ

## A. เตรียมฐานข้อมูล Neon

1. สร้าง project/database บน Neon.
2. คัดลอก connection string จากหน้า **Connect** โดยใช้ pooled connection ถ้ามี.
3. เก็บ URI ไว้เป็นความลับ และปรับ scheme เป็น `postgresql+psycopg://` หากยังเป็น `postgresql://`.
4. แอปจะสร้างตาราง `users`, `foods`, `meals` และเพิ่มรายการอาหารเริ่มต้นตอน backend start โดยใช้ SQLAlchemy model ใน `backend/database.py`.

## B. Deploy Backend + model ที่ Hugging Face Spaces

1. สร้าง Space ใหม่ เลือก SDK เป็น **Docker**.
2. Push repository นี้ไปยัง Space; ให้ `Dockerfile` และ `README.md` ที่มี metadata `sdk: docker` อยู่ที่ root.
3. ใส่ model TorchScript จริงไว้ใน `backend/model/foodcal.pt` และคลาสจริงใน `backend/model/classes.json` ก่อน push. ตรวจว่าขนาดไฟล์เหมาะกับ Git LFS/ข้อจำกัด Space.
4. ใน Space **Settings → Variables and secrets** ตั้ง:
   - `DATABASE_URL`: Neon Postgres URI แบบ secret.
   - `JWT_SECRET`: สุ่ม secret ยาวอย่างน้อย 32 ตัว แบบ secret. สร้างได้ด้วย `openssl rand -hex 32`.
   - `CORS_ORIGINS`: ใส่ URL production ของ Vercel แบบ origin เท่านั้น เช่น `https://foodcal.vercel.app` (ไม่เติม path หรือ slash ปิดท้าย).
   - `DEMO_LOGIN_ENABLED`: `false` (ห้ามเปิดบัญชี demo ต่อสาธารณะ).
   - `MODEL_PATH`: `/app/backend/model/foodcal.pt`.
   - `CLASSES_PATH`: `/app/backend/model/classes.json`.
5. รอ Space build/run แล้วทดสอบ `https://<space-name>.hf.space/health` และ `https://<space-name>.hf.space/docs`.
6. สร้าง admin สำหรับ Neon DB **หลัง backend start ครั้งแรก** จากเครื่องที่มี dependencies ของ backend โดยตั้ง `DATABASE_URL` เป็น Neon URI และ `JWT_SECRET` ให้ตรงกับ Space แล้วรัน `python -m backend.create_admin --email admin@example.com --name Admin`. กรอกรหัสผ่านอย่างน้อย 12 ตัวที่ prompt; ห้ามใส่ URI/secret ใน Git. CLI จะสร้าง schema/seed ใน Neon และสร้าง admin.
7. สามารถใช้คำสั่ง CLI เดิมเพื่อสร้าง admin ได้เพียงครั้งแรก; จากนั้น admin เพิ่ม user ในหน้าเว็บไซต์. หากมี admin อยู่แล้ว คำสั่งจะปฏิเสธสร้างซ้ำ.

## C. Deploy Frontend ที่ Vercel

1. ใน `frontend/config.js`, ตั้ง `API_BASE_URL` เป็น URL ของ Space เช่น `https://foodcal-demo.hf.space` (ไม่เติม `/api`).
2. Push repository ไป GitHub/GitLab ที่เชื่อมกับ Vercel.
3. ใน Vercel เลือก **Add New → Project**, import repository นี้.
4. ตั้ง **Framework Preset: Other**, **Root Directory: `.`**, ไม่ใช้ Build Command และ **Output Directory: `frontend`** (ตรงกับ `vercel.json`).
5. กด Deploy. เมื่อได้ URL จริง ให้นำ origin นั้นไปใส่ `CORS_ORIGINS` ใน Hugging Face Space แล้ว restart Space.
6. ทดสอบล็อกอินด้วย admin ที่สร้างไว้ แล้วให้ admin สร้าง user 2–3 คน. ตรวจวิเคราะห์รูป, บันทึกมื้อ และดูประวัติ.

ถ้าต้องการใช้ Vercel Preview URL ให้เพิ่ม origin ที่ต้องใช้ใน `CORS_ORIGINS` แล้ว restart Space. อย่าใช้ wildcard เปิด CORS กว้างใน production.

## D. รันในเครื่องโดยไม่ใช้ Docker

Python 3.11/3.12 แนะนำ, เปิด Terminal ที่ root ของ repository:

1. สร้าง/activate virtual environment และติดตั้ง API dependencies: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r backend/requirements.txt`.
2. ติดตั้ง CPU PyTorch: `pip install torch --index-url https://download.pytorch.org/whl/cpu`.
3. สร้าง secret: `export JWT_SECRET="$(openssl rand -hex 32)"`.
4. สำหรับบัญชีทดลอง local เท่านั้น: `export DEMO_LOGIN_ENABLED=true`.
5. เริ่ม backend: `uvicorn backend.app:app --reload --port 8000`.
6. เปิด Terminal อีกอันที่ root แล้วเริ่ม frontend: `python3 -m http.server 8080 --directory frontend --bind 127.0.0.1`.
7. เปิด `http://localhost:8080`. ค่า CORS เริ่มต้นยอมรับ localhost:8080. ใน local ใช้ SQLite ที่ `data/foodcal.db`; demo users จะ seed ให้เมื่อเปิด `DEMO_LOGIN_ENABLED=true`.
8. หยุดแต่ละ server ด้วย `Ctrl+C`. อย่าใช้บัญชี demo หรือเปิด flag นี้บนระบบ public.

หากไม่มี `foodcal.pt` backend ยังเริ่มได้ แต่ endpoint ทำนายจะตอบว่า model ยังไม่พร้อม. ชื่อใน `classes.json` ต้องตรงกับ `food_key` ใน `database/foods_seed.json`; preprocessing ใน `backend/inference.py` ต้องตรงกับตอน train.
