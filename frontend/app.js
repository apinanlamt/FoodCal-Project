(() => {
  const config = window.FOODCAL_CONFIG || {};
  const apiBase = String(config.API_BASE_URL || "").replace(/\/$/, "");
  const input = document.querySelector("#photo-input");
  const preview = document.querySelector("#image-preview");
  const placeholder = document.querySelector("#upload-placeholder");
  const analyzeButton = document.querySelector("#analyze-button");
  const statusMessage = document.querySelector("#status-message");
  const dropZone = document.querySelector("#drop-zone");
  const authMessage = document.querySelector("#auth-message");
  const authForm = document.querySelector("#auth-form");
  const createUserForm = document.querySelector("#create-user-form");
  const demoLoginPanel = document.querySelector("#demo-login-panel");
  const demoLoginList = document.querySelector("#demo-login-list");
  const cameraButton = document.querySelector("#camera-button");
  const cameraPanel = document.querySelector("#camera-panel");
  const cameraVideo = document.querySelector("#camera-video");
  const cameraDevice = document.querySelector("#camera-device");
  const classifierSelect = document.querySelector("#classifier-select");
  let cameraStream = null;
  let selectedFile = null;
  let currentResult = null;
  let previewUrl = null;
  let session = null;
  let activeUserId = null;

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`);
    const response = await fetch(`${apiBase}${path}`, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && session) {
        sessionStorage.removeItem("foodcal-access-token");
        applySession(null);
      }
      const detail = typeof data.detail === "string" ? data.detail : "เกิดข้อผิดพลาด โปรดลองอีกครั้ง";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function setStatus(message, kind = "") {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${kind}`.trim();
  }

  function setAuthMessage(message, kind = "") {
    authMessage.textContent = message;
    authMessage.className = `auth-message ${kind}`.trim();
  }

  function applySession(nextSession) {
    const nextUserId = nextSession?.user?.id || null;
    const userChanged = activeUserId !== nextUserId;
    session = nextSession;
    activeUserId = nextUserId;
    document.querySelector("#signed-out-panel").hidden = Boolean(session);
    document.querySelector("#signed-in-panel").hidden = !session;
    document.querySelector("#analyze").hidden = !session;
    document.querySelector("#history").hidden = !session;
    document.querySelector("#admin-tools").hidden = session?.user?.role !== "admin";

    if (userChanged) {
      currentResult = null;
      selectedFile = null;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      preview.removeAttribute("src");
      preview.hidden = true;
      placeholder.hidden = false;
      analyzeButton.disabled = true;
      document.querySelector("#result-content").hidden = true;
      document.querySelector("#empty-result").hidden = false;
    }

    if (session) {
      document.querySelector("#account-email").textContent = session.user.display_name || session.user.email || "บัญชี FoodCal";
      setAuthMessage("");
      if (userChanged) loadHistory();
    } else {
      currentResult = null;
      document.querySelector("#history-list").innerHTML = '<p class="history-empty">เข้าสู่ระบบเพื่อดูประวัติมื้อของคุณ</p>';
      document.querySelector("#history-count").textContent = "0 มื้อ";
      document.querySelector("#result-content").hidden = true;
      document.querySelector("#empty-result").hidden = false;
      setStatus("กรุณาเข้าสู่ระบบก่อนวิเคราะห์อาหาร");
    }
  }

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = document.querySelector("#auth-submit");
    const email = document.querySelector("#auth-email").value.trim();
    const password = document.querySelector("#auth-password").value;
    submitButton.disabled = true;
    setAuthMessage("กำลังเข้าสู่ระบบ…");
    try {
      const result = await request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      sessionStorage.setItem("foodcal-access-token", result.access_token);
      applySession({ access_token: result.access_token, user: result.user });
      authForm.reset();
      setAuthMessage("เข้าสู่ระบบสำเร็จ", "success");
    } catch (error) {
      setAuthMessage(error.message || "ดำเนินการไม่สำเร็จ กรุณาลองอีกครั้ง", "error");
    } finally {
      submitButton.disabled = false;
    }
  });

  document.querySelector("#signout-button").addEventListener("click", async () => {
    sessionStorage.removeItem("foodcal-access-token");
    applySession(null);
  });

  createUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#create-user-message");
    const submitButton = createUserForm.querySelector("button[type='submit']");
    submitButton.disabled = true;
    message.textContent = "กำลังสร้างบัญชี…";
    try {
      const user = await request("/api/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: document.querySelector("#new-user-name").value.trim(),
          email: document.querySelector("#new-user-email").value.trim(),
          password: document.querySelector("#new-user-password").value,
        }),
      });
      message.textContent = `สร้างบัญชี ${user.email} แล้ว`;
      message.className = "auth-message success";
      createUserForm.reset();
    } catch (error) {
      message.textContent = error.message;
      message.className = "auth-message error";
    } finally {
      submitButton.disabled = false;
    }
  });

  async function restoreSession() {
    const token = sessionStorage.getItem("foodcal-access-token");
    if (!token) return;
    session = { access_token: token };
    try {
      const user = await request("/api/auth/me");
      applySession({ access_token: token, user });
    } catch (error) {
      if (error.status === 401) {
        sessionStorage.removeItem("foodcal-access-token");
      } else {
        setAuthMessage("เชื่อมต่อ backend เพื่อคืนสถานะบัญชีไม่ได้ กรุณาลองรีเฟรชอีกครั้ง", "error");
      }
      applySession(null);
    }
  }

  async function loadDemoUsers() {
    try {
      const users = await request("/api/auth/demo-users");
      if (!Array.isArray(users) || users.length === 0) return;
      demoLoginList.replaceChildren();
      users.forEach((user) => {
        const card = document.createElement("div");
        card.className = "demo-login-card";
        const details = document.createElement("div");
        details.className = "demo-login-details";
        const name = document.createElement("strong");
        name.textContent = user.display_name;
        const email = document.createElement("span");
        email.textContent = user.email;
        const password = document.createElement("span");
        password.textContent = `รหัสผ่าน: ${user.password}`;
        const button = document.createElement("button");
        button.className = "demo-login-button";
        button.type = "button";
        button.textContent = "เข้าใช้";
        button.addEventListener("click", () => {
          document.querySelector("#auth-email").value = user.email;
          document.querySelector("#auth-password").value = user.password;
          authForm.requestSubmit();
        });
        details.append(name, email, password);
        card.append(details, button);
        demoLoginList.append(card);
      });
      demoLoginPanel.hidden = false;
    } catch {
      // The demo endpoint is intentionally disabled outside local demo mode.
      demoLoginPanel.hidden = true;
    }
  }

  function useFile(file) {
    if (!file) return;
    if (!new Set(["image/jpeg", "image/png", "image/webp"]).has(file.type)) {
      setStatus("รองรับเฉพาะ JPG, PNG และ WEBP หากเป็น HEIC ให้บันทึกเป็น JPG ก่อน", "error");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setStatus("ไฟล์ใหญ่เกิน 8 MB กรุณาเลือกรูปที่เล็กลง", "error");
      return;
    }
    selectedFile = file;
    currentResult = null;
    analyzeButton.disabled = false;
    document.querySelector("#save-meal-button").disabled = true;
    document.querySelector("#result-content").hidden = true;
    document.querySelector("#empty-result").hidden = false;
    document.querySelector("#result-badge").textContent = "พร้อมวิเคราะห์";
    document.querySelector("#result-badge").classList.remove("ready");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
    preview.hidden = false;
    placeholder.hidden = true;
    setStatus("รูปพร้อมแล้ว กดวิเคราะห์จานนี้ได้เลย");
  }

  document.querySelector("#choose-button").addEventListener("click", () => {
    input.removeAttribute("capture");
    input.click();
  });
  function stopCamera() {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
    cameraPanel.hidden = true;
    cameraButton.disabled = false;
  }

  async function refreshCameraDevices(selectedDeviceId = "") {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === "videoinput");
    cameraDevice.replaceChildren();
    cameras.forEach((device, index) => {
      const option = document.createElement("option");
      option.value = device.deviceId;
      option.textContent = device.label || `กล้อง ${index + 1}`;
      cameraDevice.append(option);
    });
    if (selectedDeviceId && cameras.some((device) => device.deviceId === selectedDeviceId)) {
      cameraDevice.value = selectedDeviceId;
    }
    cameraDevice.disabled = cameras.length < 2;
  }

  async function startCamera(deviceId = "") {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("เบราว์เซอร์นี้เปิดกล้องไม่ได้ กรุณาใช้ Chrome หรือ Safari เวอร์ชันปัจจุบัน", "error");
      return;
    }
    cameraButton.disabled = true;
    setStatus("กำลังเชื่อมต่อกล้อง…");
    try {
      cameraStream?.getTracks().forEach((track) => track.stop());
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } },
      });
      cameraVideo.srcObject = cameraStream;
      cameraPanel.hidden = false;
      await cameraVideo.play();
      await refreshCameraDevices(cameraStream.getVideoTracks()[0]?.getSettings().deviceId || deviceId);
      setStatus("กล้องพร้อมแล้ว จัดภาพอาหารแล้วกดถ่ายภาพได้เลย");
    } catch (error) {
      stopCamera();
      const message = error.name === "NotAllowedError"
        ? "ไม่ได้รับอนุญาตใช้กล้อง กรุณาอนุญาตกล้องในการตั้งค่าเบราว์เซอร์หรือ macOS"
        : error.name === "NotFoundError"
          ? "ไม่พบกล้องที่ใช้งานได้ ลองเชื่อมต่อ iPhone ใหม่หรือเลือกกล้องอื่น"
          : "เปิดกล้องไม่สำเร็จ กรุณาปิดแอปอื่นที่กำลังใช้กล้องแล้วลองอีกครั้ง";
      setStatus(message, "error");
    }
  }

  cameraButton.addEventListener("click", () => startCamera());
  document.querySelector("#close-camera-button").addEventListener("click", () => {
    stopCamera();
    setStatus("ปิดกล้องแล้ว");
  });
  cameraDevice.addEventListener("change", () => startCamera(cameraDevice.value));
  document.querySelector("#capture-button").addEventListener("click", () => {
    if (!cameraVideo.videoWidth || !cameraVideo.videoHeight) {
      setStatus("กล้องยังเตรียมภาพไม่เสร็จ ลองอีกครั้งครับ", "error");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = cameraVideo.videoWidth;
    canvas.height = cameraVideo.videoHeight;
    canvas.getContext("2d").drawImage(cameraVideo, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        setStatus("บันทึกภาพจากกล้องไม่สำเร็จ ลองอีกครั้งครับ", "error");
        return;
      }
      const imageFile = new File([blob], `foodcal-${Date.now()}.jpg`, { type: "image/jpeg" });
      stopCamera();
      useFile(imageFile);
    }, "image/jpeg", 0.92);
  });
  navigator.mediaDevices?.addEventListener("devicechange", () => {
    if (cameraStream) refreshCameraDevices(cameraVideo.srcObject?.getVideoTracks()[0]?.getSettings().deviceId || "");
  });
  window.addEventListener("pagehide", stopCamera);
  input.addEventListener("change", () => useFile(input.files?.[0]));

  ["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("drag-over");
  }));
  dropZone.addEventListener("drop", (event) => useFile(event.dataTransfer?.files?.[0]));

  function formatNumber(value, digits = 0) {
    if (value === null || value === undefined) return "—";
    return new Intl.NumberFormat("th-TH", { maximumFractionDigits: digits }).format(value);
  }

  function nutritionSourceLabel(source) {
    if (source?.fdc_id) {
      const dataset = source.data_type === "SR Legacy" ? "USDA SR Legacy (2018)" : "USDA FNDDS 2021–2023";
      const match = source.match_quality === "approximate" ? `${dataset} · รายการใกล้เคียง` : dataset;
      const sourceLink = source.source_item?.startsWith("https://fdc.nal.usda.gov/food-details/")
        ? ` · <a href="${escapeHtml(source.source_item)}" target="_blank" rel="noopener noreferrer">ดูข้อมูล USDA ต้นทาง ↗</a>`
        : "";
      const referenceServing = source.reference_serving && source.reference_serving_g
        ? ` · หน่วยอ้างอิง ${escapeHtml(source.reference_serving)} (${formatNumber(source.reference_serving_g)} กรัม)`
        : "";
      return `${match}: ${escapeHtml(source.fdc_description || "รายการอาหาร")} (FDC ${formatNumber(source.fdc_id)})${referenceServing}${sourceLink}`;
    }
    return "ค่าประมาณชั่วคราวที่ยังไม่ตรวจสอบ; ไม่มีรายการ USDA ที่จับคู่ได้";
  }

  function nutritionSourceSummary(source) {
    if (!source?.fdc_id) return "ค่าประมาณชั่วคราว";
    const dataset = source.data_type === "SR Legacy" ? "SR Legacy" : "FNDDS";
    return `${source.match_quality === "approximate" ? `USDA ใกล้เคียง (${dataset})` : `USDA ${dataset}`} · FDC ${source.fdc_id}`;
  }

  function renderNutrition(result) {
    const nutrition = result.nutrition;
    const modelLabel = result.model_name || "Food-101";
    const classCount = result.class_count || (result.model === "thfood50" ? 50 : 101);
    document.querySelector("#model-result-label").textContent = `FOOD MATCH · ${modelLabel.toUpperCase()}`;
    document.querySelector("#food-name").textContent = result.food_name || result.predicted_label;
    document.querySelector("#food-confidence").textContent = `คะแนนอันดับ 1 ${formatNumber(result.confidence * 100, 1)}% · จาก ${classCount} คลาส`;
    document.querySelector("#prediction-note").textContent = `คะแนนเป็น softmax score ไม่ใช่โอกาสถูกที่ผ่านการปรับเทียบ · ใช้ผลภายในโมเดล ${modelLabel} เท่านั้น`;
    const predictions = result.top_predictions || [{
      label: result.predicted_label,
      food_name: result.food_name || result.predicted_label,
      score: result.confidence,
    }];
    document.querySelector("#prediction-list").innerHTML = predictions.map((item, index) => `
      <li class="prediction-row${index === 0 ? " is-leading" : ""}">
        <span class="prediction-rank">${index + 1}</span>
        <span class="prediction-name">${escapeHtml(item.food_name || item.label.replaceAll("_", " "))}</span>
        <span class="prediction-score">${formatNumber(item.score * 100, 1)}%</span>
        <span class="prediction-meter"><i style="width:${Math.min(100, item.score * 100)}%"></i></span>
      </li>`).join("");
    document.querySelector("#calories-value").textContent = formatNumber(nutrition?.calories_kcal);
    document.querySelector("#protein-value").innerHTML = `${formatNumber(nutrition?.protein_g, 1)}<small> g</small>`;
    document.querySelector("#carbs-value").innerHTML = `${formatNumber(nutrition?.carbs_g, 1)}<small> g</small>`;
    document.querySelector("#fat-value").innerHTML = `${formatNumber(nutrition?.fat_g, 1)}<small> g</small>`;
    const nutritionServing = document.querySelector("#nutrition-serving");
    if (nutrition) {
      const per100g = nutrition.calories_kcal * 100 / result.servings_g;
      const macroNote = valuesHaveMacros(nutrition) ? "" : " · ยังไม่มีข้อมูลโปรตีน คาร์โบไฮเดรต และไขมัน";
      nutritionServing.innerHTML = `คำนวณสำหรับ ${formatNumber(result.servings_g)} กรัม · ${formatNumber(per100g, 1)} kcal ต่อ 100 กรัม · สูตรจริงอาจต่างกัน${macroNote}<span class="nutrition-provenance">${nutritionSourceLabel(result.nutrition_source)}</span>`;
    } else {
      nutritionServing.textContent = "ยังไม่มีข้อมูลโภชนาการของอาหารชนิดนี้ในฐานข้อมูล";
    }
    const values = [nutrition?.protein_g, nutrition?.carbs_g, nutrition?.fat_g];
    ["protein", "carbs", "fat"].forEach((name, index) => {
      const bar = document.querySelector(`#${name}-bar`);
      bar.style.width = nutrition && values[index] != null ? `${Math.min(100, (values[index] / 50) * 100)}%` : "0%";
    });
    document.querySelector("#empty-result").hidden = true;
    document.querySelector("#result-content").hidden = false;
    document.querySelector("#result-badge").textContent = "วิเคราะห์แล้ว";
    document.querySelector("#result-badge").classList.add("ready");
    document.querySelector("#save-meal-button").disabled = !result.food_id || !nutrition;
  }

  function valuesHaveMacros(nutrition) {
    return nutrition.protein_g !== null && nutrition.carbs_g !== null && nutrition.fat_g !== null;
  }

  analyzeButton.addEventListener("click", async () => {
    if (!selectedFile) return;
    const serving = Number(document.querySelector("#serving-input").value);
    if (!Number.isFinite(serving) || serving < 1 || serving > 2000) {
      setStatus("ปริมาณต้องอยู่ระหว่าง 1–2,000 กรัม", "error");
      return;
    }
    const body = new FormData();
    body.append("file", selectedFile);
    body.append("servings_g", String(serving));
    body.append("model_name", classifierSelect.value);
    analyzeButton.disabled = true;
    analyzeButton.textContent = "กำลังวิเคราะห์…";
    setStatus("กำลังส่งภาพให้โมเดลวิเคราะห์ โปรดรอสักครู่");
    try {
      currentResult = await request("/api/predict", { method: "POST", body });
      renderNutrition(currentResult);
      setStatus(currentResult.nutrition ? "วิเคราะห์เสร็จแล้ว · ค่าแคลอรีเป็นค่าประมาณจากแหล่งข้อมูลที่แสดง" : "ไม่พบข้อมูลโภชนาการสำหรับคลาสนี้", currentResult.nutrition ? "success" : "");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      analyzeButton.disabled = !selectedFile;
      analyzeButton.innerHTML = 'วิเคราะห์จานนี้ <span aria-hidden="true">→</span>';
    }
  });

  document.querySelector("#save-meal-button").addEventListener("click", async (event) => {
    if (!currentResult?.food_id) return;
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await request("/api/meals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          food_id: currentResult.food_id,
          servings_g: currentResult.servings_g,
          confidence: currentResult.confidence,
          predicted_label: currentResult.predicted_label,
        }),
      });
      setStatus("บันทึกมื้ออาหารแล้ว", "success");
      await loadHistory();
    } catch (error) {
      setStatus(error.message, "error");
      button.disabled = false;
    }
  });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  async function loadHistory() {
    const list = document.querySelector("#history-list");
    if (!session) return;
    try {
      const meals = await request("/api/meals");
      document.querySelector("#history-count").textContent = `${meals.length} มื้อ`;
      if (!meals.length) {
        list.innerHTML = '<p class="history-empty">มื้อที่บันทึกจะแสดงตรงนี้ เริ่มต้นจากการวิเคราะห์อาหารสักจานนะ</p>';
        return;
      }
      list.innerHTML = meals.map((meal) => `
        <article class="history-row">
          <span class="history-thumb" aria-hidden="true">✿</span>
          <div><div class="history-food">${escapeHtml(meal.food_name)}</div><div class="history-date">${new Date(meal.created_at).toLocaleString("th-TH")} · ${formatNumber(meal.servings_g)} กรัม · ${nutritionSourceSummary(meal.nutrition_source)}</div></div>
          <strong class="history-calories">${formatNumber(meal.calories_kcal)} <small>kcal โดยประมาณ</small></strong>
          <button class="history-delete" type="button" data-delete-id="${meal.id}" aria-label="ลบรายการ ${escapeHtml(meal.food_name)}">×</button>
        </article>`).join("");
      list.querySelectorAll("[data-delete-id]").forEach((button) => button.addEventListener("click", async () => {
        try {
          await request(`/api/meals/${button.dataset.deleteId}`, { method: "DELETE" });
          await loadHistory();
        } catch (error) {
          setStatus(error.message, "error");
        }
      }));
    } catch (error) {
      list.innerHTML = `<p class="history-empty">โหลดประวัติไม่ได้: ${escapeHtml(error.message)}</p>`;
    }
  }

  restoreSession();
  loadDemoUsers();
})();
