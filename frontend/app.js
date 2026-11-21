(() => {
  const config = window.FOODCAL_CONFIG || {};
  const apiBase = String(config.API_BASE_URL || "").replace(/\/$/, "");
  const input = document.querySelector("#photo-input");
  const preview = document.querySelector("#image-preview");
  const placeholder = document.querySelector("#upload-placeholder");
  const analyzeButton = document.querySelector("#analyze-button");
  const statusMessage = document.querySelector("#status-message");
  const dropZone = document.querySelector("#drop-zone");
  const servingInput = document.querySelector("#serving-input");
  const servingSlider = document.querySelector("#serving-slider");
  const servingOutput = document.querySelector("#serving-output");
  const imageScan = document.querySelector("#image-scan");
  const analysisProgress = document.querySelector("#analysis-progress");
  let selectedFile = null;
  let currentResult = null;
  let previewUrl = null;
  let analysisProgressTimer = null;
  let analysisHideTimer = null;

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
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
    imageScan.hidden = true;
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

  input.addEventListener("click", () => { input.value = ""; });
  input.addEventListener("change", () => useFile(input.files?.[0]));
  document.querySelector("#choose-button").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });

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

  function syncServing(value, updateResult = true) {
    const grams = Number(value);
    if (!Number.isFinite(grams) || grams < 1 || grams > 2000) return;
    servingInput.value = String(grams);
    servingSlider.value = String(grams);
    servingOutput.textContent = `${formatNumber(grams)} กรัม`;
    if (!updateResult || !currentResult) return;

    currentResult.servings_g = grams;
    if (currentResult.nutrition && currentResult._nutritionPer100g) {
      currentResult.nutrition = Object.fromEntries(
        Object.entries(currentResult._nutritionPer100g).map(([key, per100g]) => [
          key,
          per100g === null ? null : Math.round((per100g * grams / 100) * 10) / 10,
        ]),
      );
      renderNutrition(currentResult);
    }
  }

  servingInput.addEventListener("input", () => syncServing(servingInput.value));
  servingSlider.addEventListener("input", () => syncServing(servingSlider.value));
  document.querySelector("#serving-decrease").addEventListener("click", () => {
    syncServing(Math.max(1, Number(servingInput.value || 250) - 25));
  });
  document.querySelector("#serving-increase").addEventListener("click", () => {
    syncServing(Math.min(2000, Number(servingInput.value || 250) + 25));
  });

  function setAnalysisStage(stage) {
    const steps = [...analysisProgress.querySelectorAll(".analysis-step")];
    steps.forEach((step, index) => {
      step.classList.toggle("is-complete", index < stage);
      step.classList.toggle("is-active", index === stage);
    });
    document.querySelector("#analysis-progress-fill").style.width = `${stage * 50}%`;
  }

  function startAnalysisProgress() {
    window.clearTimeout(analysisHideTimer);
    analysisProgress.hidden = false;
    imageScan.hidden = false;
    setAnalysisStage(0);
    let stage = 0;
    analysisProgressTimer = window.setInterval(() => {
      stage = Math.min(stage + 1, 2);
      setAnalysisStage(stage);
    }, 900);
  }

  function finishAnalysisProgress(completed) {
    window.clearInterval(analysisProgressTimer);
    analysisProgressTimer = null;
    analysisProgress.querySelectorAll(".analysis-step").forEach((step) => {
      step.classList.remove("is-active");
      step.classList.toggle("is-complete", completed);
    });
    document.querySelector("#analysis-progress-fill").style.width = completed ? "100%" : "0%";
    imageScan.hidden = true;
    analysisHideTimer = window.setTimeout(() => { analysisProgress.hidden = true; }, 650);
  }

  function nutritionSourceLabel(source) {
    if (source?.source && !source?.fdc_id) {
      const match = source.match_quality === "approximate" ? "เมนูใกล้เคียง" : "จับคู่ตรงเมนู";
      const sourceLink = source.source_item
        ? ` · <a href="${escapeHtml(source.source_item)}" target="_blank" rel="noopener noreferrer">ดูแหล่งข้อมูล ↗</a>`
        : "";
      const note = source.match_note ? ` · ${escapeHtml(source.match_note)}` : "";
      return `${match}: ${escapeHtml(source.source)}${note}${sourceLink}`;
    }
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
    if (source?.source && !source?.fdc_id) {
      return `${source.match_quality === "approximate" ? "แหล่งไทยใกล้เคียง" : "แหล่งข้อมูลไทย"}`;
    }
    if (!source?.fdc_id) return "ค่าประมาณชั่วคราว";
    const dataset = source.data_type === "SR Legacy" ? "SR Legacy" : "FNDDS";
    return `${source.match_quality === "approximate" ? `USDA ใกล้เคียง (${dataset})` : `USDA ${dataset}`} · FDC ${source.fdc_id}`;
  }

  function renderNutrition(result) {
    const nutrition = result.nutrition;
    if (nutrition && !result._nutritionPer100g && result.servings_g > 0) {
      result._nutritionPer100g = result.nutrition_per_100g || Object.fromEntries(
        Object.entries(nutrition).map(([key, value]) => [key, value === null ? null : value * 100 / result.servings_g]),
      );
    }
    const modelLabel = result.model_name || "Food-101";
    const classCount = result.class_count || (result.model === "thfood50" ? 50 : 101);
    document.querySelector("#model-result-label").textContent = `FOOD MATCH · ${modelLabel.toUpperCase()}`;
    document.querySelector("#food-name").textContent = result.food_name || result.predicted_label;
    document.querySelector("#food-confidence").textContent = `คะแนนอันดับ 1 ${formatNumber(result.confidence * 100, 1)}% · จาก ${classCount} คลาส`;
    document.querySelector("#prediction-note").textContent = result.selection_mode === "automatic"
      ? `เลือกรุ่นอัตโนมัติ · คะแนน softmax ใช้ดูภายใน ${modelLabel} เท่านั้น และไม่ใช่โอกาสถูกที่ผ่านการปรับเทียบ`
      : `คะแนน softmax ไม่ใช่โอกาสถูกที่ผ่านการปรับเทียบ · ใช้ผลภายในโมเดล ${modelLabel} เท่านั้น`;
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
    [servingInput, servingSlider, document.querySelector("#serving-decrease"), document.querySelector("#serving-increase")]
      .forEach((control) => { control.disabled = true; });
    analyzeButton.disabled = true;
    analyzeButton.textContent = "กำลังวิเคราะห์…";
    startAnalysisProgress();
    setStatus("กำลังอ่านภาพและจับคู่ข้อมูลโภชนาการ โปรดรอสักครู่");
    let completed = false;
    try {
      currentResult = await request("/api/predict", { method: "POST", body });
      renderNutrition(currentResult);
      syncServing(currentResult.servings_g, false);
      completed = true;
      setStatus(currentResult.nutrition ? "วิเคราะห์เสร็จแล้ว · ค่าแคลอรีเป็นค่าประมาณจากแหล่งข้อมูลที่แสดง" : "ไม่พบข้อมูลโภชนาการสำหรับคลาสนี้", currentResult.nutrition ? "success" : "");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      finishAnalysisProgress(completed);
      [servingInput, servingSlider, document.querySelector("#serving-decrease"), document.querySelector("#serving-increase")]
        .forEach((control) => { control.disabled = false; });
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
    try {
      const meals = await request("/api/meals");
      document.querySelector("#history-count").textContent = `${meals.length} มื้อ`;
      renderWeeklySummary(meals);
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

  function localDateKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function renderWeeklySummary(meals) {
    const summary = document.querySelector("#weekly-summary");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - 6 + index);
      return {
        date,
        key: localDateKey(date),
        label: new Intl.DateTimeFormat("th-TH", { weekday: "short" }).format(date),
        calories: 0,
        protein: 0,
        carbs: 0,
        fat: 0,
        proteinKnown: 0,
        carbsKnown: 0,
        fatKnown: 0,
        meals: 0,
      };
    });
    const dayByKey = new Map(days.map((day) => [day.key, day]));
    meals.forEach((meal) => {
      const date = new Date(meal.created_at);
      if (Number.isNaN(date.getTime())) return;
      const day = dayByKey.get(localDateKey(date));
      if (!day) return;
      day.calories += Number(meal.calories_kcal) || 0;
      if (meal.protein_g !== null && meal.protein_g !== undefined) {
        day.protein += Number(meal.protein_g) || 0;
        day.proteinKnown += 1;
      }
      if (meal.carbs_g !== null && meal.carbs_g !== undefined) {
        day.carbs += Number(meal.carbs_g) || 0;
        day.carbsKnown += 1;
      }
      if (meal.fat_g !== null && meal.fat_g !== undefined) {
        day.fat += Number(meal.fat_g) || 0;
        day.fatKnown += 1;
      }
      day.meals += 1;
    });

    const weekMeals = days.reduce((sum, day) => sum + day.meals, 0);
    const calorieTotal = days.reduce((sum, day) => sum + day.calories, 0);
    const proteinTotal = days.reduce((sum, day) => sum + day.protein, 0);
    const carbsTotal = days.reduce((sum, day) => sum + day.carbs, 0);
    const fatTotal = days.reduce((sum, day) => sum + day.fat, 0);
    const calorieScale = Math.max(500, ...days.map((day) => day.calories));
    const macroScale = Math.max(30, ...days.flatMap((day) => [day.protein, day.carbs, day.fat]));
    const proteinDays = days.filter((day) => day.proteinKnown > 0).length;
    const carbsDays = days.filter((day) => day.carbsKnown > 0).length;
    const fatDays = days.filter((day) => day.fatKnown > 0).length;
    const proteinWeekTotal = proteinDays ? formatNumber(proteinTotal, 1) : "—";
    const calorieBars = days.map((day) => {
      const height = day.calories ? Math.max(4, day.calories / calorieScale * 100) : 0;
      return `<div class="weekly-day" title="${day.date.toLocaleDateString("th-TH")}: ${formatNumber(day.calories)} kcal จาก ${day.meals} มื้อ"><span class="weekly-day-value">${day.calories ? formatNumber(day.calories) : "—"}</span><div class="weekly-calorie-track"><i style="height:${height}%"></i></div><span class="weekly-day-label">${day.label}</span></div>`;
    }).join("");
    const macroBars = days.map((day) => `
      <div class="weekly-macro-day" title="${day.date.toLocaleDateString("th-TH")}: โปรตีน ${day.proteinKnown ? `${formatNumber(day.protein, 1)} g` : "ไม่มีข้อมูล"} · คาร์บ ${day.carbsKnown ? `${formatNumber(day.carbs, 1)} g` : "ไม่มีข้อมูล"} · ไขมัน ${day.fatKnown ? `${formatNumber(day.fat, 1)} g` : "ไม่มีข้อมูล"}">
        <span>${day.label}</span><div class="weekly-macro-bars">
          <i class="weekly-protein" style="height:${day.protein / macroScale * 52}px"></i>
          <i class="weekly-carbs" style="height:${day.carbs / macroScale * 52}px"></i>
          <i class="weekly-fat" style="height:${day.fat / macroScale * 52}px"></i>
        </div>
      </div>`).join("");

    summary.innerHTML = `
      <section class="weekly-card" aria-label="สรุปอาหารย้อนหลัง 7 วัน">
        <div class="weekly-card-heading"><div><p class="eyebrow">YOUR LAST 7 DAYS</p><h3>ภาพรวม 7 วัน</h3></div><span>ยอดรวม 7 วัน</span></div>
        <div class="weekly-stats">
          <div><span>พลังงานรวม</span><strong>${formatNumber(calorieTotal)} <small>kcal</small></strong></div>
          <div><span>โปรตีนรวม*</span><strong>${proteinWeekTotal} <small>g</small></strong></div>
          <div><span>บันทึกมื้อ</span><strong>${formatNumber(weekMeals)} <small>มื้อ</small></strong></div>
        </div>
        ${weekMeals ? `
          <div class="weekly-chart-section"><div class="weekly-chart-title"><strong>แคลอรีแต่ละวัน</strong><span>kcal</span></div><div class="weekly-calorie-chart">${calorieBars}</div></div>
          <div class="weekly-chart-section"><div class="weekly-chart-title"><strong>สารอาหารหลักแต่ละวัน</strong><div class="weekly-legend"><span><i class="weekly-protein"></i>P</span><span><i class="weekly-carbs"></i>C</span><span><i class="weekly-fat"></i>F</span></div></div><div class="weekly-macro-chart">${macroBars}</div><p class="weekly-macro-caption">เฉลี่ยในวันที่มีข้อมูล: โปรตีน ${proteinDays ? `${formatNumber(proteinTotal / proteinDays, 1)} g` : "—"} · คาร์โบไฮเดรต ${carbsDays ? `${formatNumber(carbsTotal / carbsDays, 1)} g` : "—"} · ไขมัน ${fatDays ? `${formatNumber(fatTotal / fatDays, 1)} g` : "—"} · *ค่าบางเมนูอาจไม่มีข้อมูลสารอาหาร</p></div>
        ` : '<p class="weekly-empty">บันทึกมื้อแรกแล้วกราฟสรุปของคุณจะแสดงที่นี่</p>'}
      </section>`;
  }

  loadHistory();
})();
