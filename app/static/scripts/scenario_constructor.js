let constructorData = null;
let currentCycle = null;
let currentSteps = [];

let isDirty = false;

function setDirty(state) {
    isDirty = state;

    const el = document.getElementById('dirty-indicator');
    if (!el) return;

    if (state) {
        el.textContent = 'Изменено, не сохранено';
        el.className = 'dirty-indicator dirty';
    } else {
        el.textContent = 'Сохранено';
        el.className = 'dirty-indicator saved';
    }
}

function minutesFromPeriodInputs() {
    const h = parseInt(document.getElementById('cycle-period-hours').value || '0', 10);
    const m = parseInt(document.getElementById('cycle-period-minutes').value || '0', 10);
    return h * 60 + m;
}

function setPeriodInputs(totalMinutes) {
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    document.getElementById('cycle-period-hours').value = h;
    document.getElementById('cycle-period-minutes').value = m;
}

async function loadConstructorData() {
    const resp = await fetch(constructorDataUrl);
    if (!resp.ok) {
        alert('Не удалось загрузить данные конструктора');
        return;
    }

    constructorData = await resp.json();

    renderCyclesList();

    if (constructorData.cycles.length > 0) {
        selectCycle(constructorData.cycles[0].id);
    } else {
        newCycle();
    }

    renderDayVisualization();
}

function renderCyclesList() {
    const box = document.getElementById('cycles-list');
    box.innerHTML = '';

    if (!constructorData.cycles.length) {
        box.innerHTML = '<div class="caption">Циклы пока не созданы.</div>';
        return;
    }

    constructorData.cycles.forEach(cycle => {
        const item = document.createElement('button');
        item.className = 'cycle-item';
        if (currentCycle && currentCycle.id === cycle.id) {
            item.classList.add('active');
        }

        const state = cycle.enabled ? 'активен' : 'отключен';

        item.innerHTML = `
            <span class="cycle-item-title">${escapeHtml(cycle.name)}</span>
            <span class="cycle-item-meta">${escapeHtml(cycle.cycle_type)} · ${escapeHtml(cycle.first_time)} · ${state}</span>
        `;

        item.onclick = () => selectCycle(cycle.id);
        box.appendChild(item);
    });
}

function selectCycle(id) {
    const cycle = constructorData.cycles.find(c => c.id === id);
    if (!cycle) return;

    currentCycle = JSON.parse(JSON.stringify(cycle));
    currentSteps = JSON.parse(JSON.stringify(cycle.steps || []));

    document.getElementById('editor-title').innerText = 'Редактор цикла';
    document.getElementById('cycle-id').value = currentCycle.id;
    document.getElementById('cycle-name').value = currentCycle.name;
    document.getElementById('cycle-type').value = currentCycle.cycle_type;
    document.getElementById('cycle-enabled').value = currentCycle.enabled ? '1' : '0';
    document.getElementById('cycle-first-time').value = currentCycle.first_time;

    setPeriodInputs(currentCycle.period_minutes);

    renderCyclesList();
    renderSteps();
    updatePreview();
	setDirty(false);
}

function newCycle() {
    currentCycle = null;
    currentSteps = [];

    document.getElementById('editor-title').innerText = 'Новый цикл';
    document.getElementById('cycle-id').value = '';
    document.getElementById('cycle-name').value = '';
    document.getElementById('cycle-type').value = 'Полив';
    document.getElementById('cycle-enabled').value = '1';
    document.getElementById('cycle-first-time').value = '01:00';

    setPeriodInputs(0);

    renderCyclesList();
    renderSteps();
    updatePreview();
	setDirty(true);
}

function getParamsForCurrentType() {
    if (!constructorData) return [];

    const type = document.getElementById('cycle-type').value;

    if (type === 'Полив') {
        return constructorData.parameters['Полив'] || [];
    }

    if (type === 'Свет') {
        return [
            ...(constructorData.parameters['Свет'] || []),
            ...(constructorData.parameters['Свет уровень'] || [])
        ];
    }

    if (type === 'Свет уровень') {
        return constructorData.parameters['Свет уровень'] || [];
    }

    return [];
}

function renderSteps() {
    const tbody = document.getElementById('steps-body');
    tbody.innerHTML = '';

    if (!currentSteps.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="caption">Нет шагов</td></tr>';
        updatePreview();
        return;
    }

    const params = getParamsForCurrentType();

    currentSteps.forEach((step, index) => {
        const tr = document.createElement('tr');

        const parameterOptions = params.map(p => {
            const selected = p.name === step.parameter ? 'selected' : '';
            return `<option value="${escapeAttr(p.name)}" ${selected}>${escapeHtml(p.name)}</option>`;
        }).join('');

        tr.innerHTML = `
    <td data-label="№">${index + 1}</td>

    <td data-label="Задержка">
        <div class="delay-grid">
            <input type="number" class="form-control"
                   min="0" max="23"
                   value="${Math.floor((step.delay_sec || 0) / 3600)}"
                   onchange="updateStepDelayPart(${index}, 'h', this.value)">
            <input type="number" class="form-control"
                   min="0" max="59"
                   value="${Math.floor(((step.delay_sec || 0) % 3600) / 60)}"
                   onchange="updateStepDelayPart(${index}, 'm', this.value)">
            <input type="number" class="form-control"
                   min="0" max="59"
                   value="${(step.delay_sec || 0) % 60}"
                   onchange="updateStepDelayPart(${index}, 's', this.value)">
        </div>
        <div class="delay-caption">часы / минуты / секунды</div>
    </td>

    <td data-label="Параметр">
        <select class="form-control" onchange="updateStepParameter(${index}, this.value)">
            ${parameterOptions}
        </select>
    </td>

    <td data-label="Значение">
        ${renderValueEditor(step, index)}
    </td>

    <td data-label="Действия">
        ${isAdmin ? `
            <div class="step-actions">
                <button class="btn" onclick="moveStepUp(${index})" ${index === 0 ? 'disabled' : ''}>↑</button>
                <button class="btn" onclick="moveStepDown(${index})" ${index === currentSteps.length - 1 ? 'disabled' : ''}>↓</button>
                <button class="btn" onclick="duplicateStep(${index})">Копия</button>
                <button class="btn btn-danger" onclick="removeStep(${index})">Удалить</button>
            </div>
        ` : ''}
    </td>
`;

        tbody.appendChild(tr);
    });

    updatePreview();
}

function renderValueEditor(step, index) {
    const type = document.getElementById('cycle-type').value;
    const params = getParamsForCurrentType();
    const param = params.find(p => p.name === step.parameter);
    const acceptable = (param && param.acceptable_values || '').toLowerCase();

    const isNumeric =
        type === 'Свет уровень' ||
        acceptable.includes('-') ||
        acceptable.includes('100') ||
        acceptable.includes('яркость');

    if (isNumeric && type !== 'Полив') {
        return `
            <input type="number"
                   class="form-control"
                   value="${escapeAttr(step.value || '0')}"
                   onchange="updateStepValue(${index}, this.value)">
        `;
    }

    return `
        <select class="form-control" onchange="updateStepValue(${index}, this.value)">
            <option value="1" ${String(step.value) === '1' ? 'selected' : ''}>включить</option>
            <option value="0" ${String(step.value) === '0' ? 'selected' : ''}>отключить</option>
        </select>
    `;
}

function addStep() {
    const params = getParamsForCurrentType();
    const firstParam = params.length ? params[0].name : '';

    currentSteps.push({
        delay_sec: currentSteps.length === 0 ? 0 : 1,
        parameter: firstParam,
        value: '1'
    });

	setDirty(true);
    renderSteps();
}

function removeStep(index) {
    currentSteps.splice(index, 1);
	setDirty(true);
    renderSteps();
}

function duplicateStep(index) {
    const copy = JSON.parse(JSON.stringify(currentSteps[index]));
    currentSteps.splice(index + 1, 0, copy);
	setDirty(true);
    renderSteps();
}

function moveStepUp(index) {
    if (index <= 0) return;

    const item = currentSteps[index];
    currentSteps[index] = currentSteps[index - 1];
    currentSteps[index - 1] = item;
	setDirty(true);
    renderSteps();
}

function moveStepDown(index) {
    if (index >= currentSteps.length - 1) return;

    const item = currentSteps[index];
    currentSteps[index] = currentSteps[index + 1];
    currentSteps[index + 1] = item;
	setDirty(true);
    renderSteps();
}

function updateStepParameter(index, value) {
    currentSteps[index].parameter = value;
    setDirty(true);
    renderSteps();
}

function updateStepValue(index, value) {
    currentSteps[index].value = value;
    setDirty(true);
    updatePreview();
}

function updateStepDelayPart(index, part, rawValue) {
    const value = Math.max(0, parseInt(rawValue || '0', 10));

    const old = currentSteps[index].delay_sec || 0;
    let h = Math.floor(old / 3600);
    let m = Math.floor((old % 3600) / 60);
    let s = old % 60;

    if (part === 'h') h = Math.min(value, 23);
    if (part === 'm') m = Math.min(value, 59);
    if (part === 's') s = Math.min(value, 59);

    currentSteps[index].delay_sec = h * 3600 + m * 60 + s;
	setDirty(true);
    updatePreview();
}

function collectCyclePayload() {
    return {
        id: document.getElementById('cycle-id').value || null,
        name: document.getElementById('cycle-name').value.trim(),
        cycle_type: document.getElementById('cycle-type').value,
        first_time: document.getElementById('cycle-first-time').value,
        period_minutes: minutesFromPeriodInputs(),
        enabled: document.getElementById('cycle-enabled').value === '1',
        steps: currentSteps
    };
}

async function saveCycle() {
    const payload = collectCyclePayload();

    if (!payload.name) {
        alert('Укажи имя цикла');
        return;
    }

    if (payload.period_minutes < 0) {
		alert('Период не может быть отрицательным');
		return;
	}

    if (!payload.steps.length) {
        alert('Добавь хотя бы один шаг');
        return;
    }

    const resp = await fetch(saveCycleUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const result = await resp.json();

    if (!result.success) {
        showToast('Ошибка сохранения цикла', 'error');
        return;
    }

    await loadConstructorData();
	selectCycle(result.id);
	renderDayVisualization();
	setDirty(false);
	showToast('Цикл сохранён');
}

async function deleteCurrentCycle() {
    const id = document.getElementById('cycle-id').value;

    if (!id) {
        newCycle();
        return;
    }

    if (!confirm('Удалить этот цикл и все созданные им строки сценариев?')) {
        return;
    }

    const resp = await fetch(deleteCycleUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    });

    const result = await resp.json();

    if (!result.success) {
        alert(result.error || 'Ошибка удаления');
        return;
    }

    await loadConstructorData();
	renderDayVisualization();
}

function updatePreview() {
    const box = document.getElementById('preview-log');
    const name = document.getElementById('cycle-name').value.trim() || 'Новый цикл';
    const firstTime = document.getElementById('cycle-first-time').value || '00:00';
    const periodMinutes = minutesFromPeriodInputs();

    if (!currentSteps.length) {
		box.innerHTML = '<div class="caption">Нет данных для предпросмотра.</div>';
		return;
	}

    const events = buildPreviewEvents(firstTime, periodMinutes, currentSteps);

    if (!events.length) {
        box.innerHTML = '<div class="caption">Расписание пустое.</div>';
        return;
    }

    box.innerHTML = `
        <div class="preview-cycle-title">${escapeHtml(name)}</div>
        <table class="table preview-table">
            <thead>
                <tr>
                    <th>Время</th>
                    <th>Шаг</th>
                    <th>Параметр</th>
                    <th>Значение</th>
                </tr>
            </thead>
            <tbody>
                ${events.map(e => `
                    <tr>
                        <td>${e.time}</td>
                        <td>${e.stepIndex + 1}</td>
                        <td>${escapeHtml(e.parameter)}</td>
                        <td>${formatValue(e.value)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function buildPreviewEvents(firstTime, periodMinutes, steps) {
    const result = [];

    const [hh, mm] = firstTime.split(':').map(v => parseInt(v || '0', 10));
    let startSec = hh * 3600 + mm * 60;
// === ОДНОРАЗОВЫЙ ЦИКЛ ===
	if (periodMinutes === 0) {
		let offset = 0;

		steps.forEach((step, stepIndex) => {
			offset += parseInt(step.delay_sec || 0, 10);
			const eventSec = startSec + offset;
			const normalizedSec = ((eventSec % 86400) + 86400) % 86400;
			const dayShift = Math.floor(eventSec / 86400);

			result.push({
				time: secondsToHHMMSS(normalizedSec) + (dayShift > 0 ? ` +${dayShift}д` : ''),
				stepIndex,
				parameter: step.parameter || '',
				value: step.value
			});
		});

		return result;
	}
    while (startSec < 86400) {
        let offset = 0;

        steps.forEach((step, stepIndex) => {
            offset += parseInt(step.delay_sec || 0, 10);
            const eventSec = startSec + offset;
            const normalizedSec = ((eventSec % 86400) + 86400) % 86400;
			const dayShift = Math.floor(eventSec / 86400);

			result.push({
				time: secondsToHHMMSS(normalizedSec) + (dayShift > 0 ? ` +${dayShift}д` : ''),
				stepIndex,
				parameter: step.parameter || '',
				value: step.value
			});
        });

        startSec += periodMinutes * 60;
    }

    return result;
}

function secondsToHHMMSS(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;

    return [
        String(h).padStart(2, '0'),
        String(m).padStart(2, '0'),
        String(s).padStart(2, '0')
    ].join(':');
}

function formatValue(value) {
    if (String(value) === '1') return 'включить';
    if (String(value) === '0') return 'отключить';
    return escapeHtml(String(value));
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function escapeAttr(value) {
    return escapeHtml(value);
}

document.addEventListener('input', function (event) {
    if (
        event.target.closest('.constructor-editor') &&
        event.target.id !== 'cycle-id'
    ) {
        setDirty(true);
        updatePreview();
    }
});

document.addEventListener('change', function (event) {
    if (
        event.target.closest('.constructor-editor') &&
        event.target.id !== 'cycle-id'
    ) {
        setDirty(true);
        updatePreview();
    }
});

function getCycleColor(index) {
    const colors = [
        '#3b82f6', '#22c55e', '#f97316', '#8b5cf6',
        '#ec4899', '#14b8a6', '#eab308', '#ef4444',
        '#06b6d4', '#84cc16', '#a855f7', '#f59e0b'
    ];
    return colors[index % colors.length];
}

function renderDayVisualization() {

    const svg = document.getElementById('cycle-day-svg');
    const legend = document.getElementById('cycle-day-legend');

    if (!svg || !legend || !constructorData) return;

    svg.innerHTML = '';
    legend.innerHTML = '';

    const cycles = constructorData.cycles || [];

    if (!cycles.length) {
        legend.innerHTML = '<div class="caption">Нет циклов для отображения.</div>';
        drawDayBase(svg);
        return;
    }

    drawDayBase(svg);

    const prepared = cycles.map((cycle, index) => {
        return {
            cycle,
            color: getCycleColor(index),
            intervals: buildCycleIntervalsForDay(cycle)
        };
    });

    prepared.forEach((item, cycleIndex) => {
        item.intervals.forEach(interval => {
            drawIntervalArc(svg, interval.start, interval.end, item.color, cycleIndex);
        });
    });
	
	drawCurrentTimeArrow(svg);

    prepared.forEach(item => {
        const row = document.createElement('div');
        row.className = 'cycle-day-legend-row';
        row.innerHTML = `
            <span class="cycle-day-color" style="background:${item.color}"></span>
            <span>${escapeHtml(item.cycle.name)}</span>
        `;
        legend.appendChild(row);
    });
}

function buildCycleIntervalsForDay(cycle) {
    const steps = cycle.steps || [];
    if (!steps.length) return [];

    const firstSec = hhmmToSeconds(cycle.first_time || '00:00');
    const periodMin = parseInt(cycle.period_minutes || 0, 10);

    let offset = 0;
    let firstEventOffset = null;
    let lastEventOffset = null;

    steps.forEach(step => {
        offset += parseInt(step.delay_sec || 0, 10);

        if (firstEventOffset === null) {
            firstEventOffset = offset;
        }

        lastEventOffset = offset;
    });

    if (firstEventOffset === null || lastEventOffset === null) {
        return [];
    }

    if (lastEventOffset <= firstEventOffset) {
        lastEventOffset = firstEventOffset + 60;
    }

    const intervals = [];

    function addInterval(cycleStartSec) {
        const start = cycleStartSec + firstEventOffset;
        const end = cycleStartSec + lastEventOffset;

        intervals.push({ start, end });
    }

    if (periodMin === 0) {
        addInterval(firstSec);
        return intervals;
    }

    let cycleStart = firstSec;

    while (cycleStart < 86400) {
        addInterval(cycleStart);
        cycleStart += periodMin * 60;
    }

    return intervals;
}

function getCycleDurationSec(steps) {
    return steps.reduce((sum, step) => {
        return sum + parseInt(step.delay_sec || 0, 10);
    }, 0);
}

function drawDayBase(svg) {
    const cx = 150;
    const cy = 150;

    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    bg.setAttribute('cx', cx);
    bg.setAttribute('cy', cy);
    bg.setAttribute('r', 82);
    bg.setAttribute('fill', 'none');
    bg.setAttribute('stroke', '#e5e7eb');
    bg.setAttribute('stroke-width', '26');
    svg.appendChild(bg);

    const inner = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    inner.setAttribute('cx', cx);
    inner.setAttribute('cy', cy);
    inner.setAttribute('r', 60);
    inner.setAttribute('fill', '#ffffff');
    svg.appendChild(inner);

    const labelRadius = 124;
	drawTimeLabelAtAngle(svg, '00:00', 0, labelRadius);
	drawTimeLabelAtAngle(svg, '06:00', 90, labelRadius);
	drawTimeLabelAtAngle(svg, '12:00', 180, labelRadius);
	drawTimeLabelAtAngle(svg, '18:00', 270, labelRadius);

    for (let h = 0; h < 24; h++) {
        const angle = secToAngle(h * 3600);
        const p1 = polarToXY(cx, cy, 99, angle);
        const p2 = polarToXY(cx, cy, h % 6 === 0 ? 112 : 106, angle);

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', p1.x);
        line.setAttribute('y1', p1.y);
        line.setAttribute('x2', p2.x);
        line.setAttribute('y2', p2.y);
        line.setAttribute('stroke', '#cbd5e1');
        line.setAttribute('stroke-width', h % 6 === 0 ? '2' : '1');
        svg.appendChild(line);
    }
}

function drawIntervalArc(svg, startSec, endSec, color, layerIndex) {
    if (endSec <= startSec) return;

    const day = 86400;

    if (endSec - startSec >= day) {
        drawArcPart(svg, 0, day, color, layerIndex);
        return;
    }

    const startNorm = ((startSec % day) + day) % day;
    const endNorm = ((endSec % day) + day) % day;

    if (startNorm < endNorm && Math.floor(startSec / day) === Math.floor(endSec / day)) {
        drawArcPart(svg, startNorm, endNorm, color, layerIndex);
    } else {
        drawArcPart(svg, startNorm, day, color, layerIndex);
        drawArcPart(svg, 0, endNorm, color, layerIndex);
    }
}

function drawArcPart(svg, startSec, endSec, color, layerIndex) {
    if (endSec <= startSec) return;

    const cx = 150;
    const cy = 150;
    const r = 82;
    const day = 86400;
    const circumference = 2 * Math.PI * r;

    const width = Math.max(5, 24 - layerIndex * 3);

    const length = ((endSec - startSec) / day) * circumference;
    const offset = -(startSec / day) * circumference;

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');

    circle.setAttribute('cx', cx);
    circle.setAttribute('cy', cy);
    circle.setAttribute('r', r);
    circle.setAttribute('fill', 'none');
    circle.setAttribute('stroke', color);
    circle.setAttribute('stroke-width', width);
    circle.setAttribute('stroke-dasharray', `${length} ${circumference - length}`);
    circle.setAttribute('stroke-dashoffset', offset);
    circle.setAttribute('stroke-linecap', 'butt');
    circle.setAttribute('opacity', layerIndex === 0 ? '0.88' : '0.70');
    circle.setAttribute('transform', `rotate(-90 ${cx} ${cy})`);

    svg.appendChild(circle);
}

function drawTimeLabel(svg, text, x, y) {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', x);
    label.setAttribute('y', y);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '13');
    label.setAttribute('fill', '#374151');
    label.textContent = text;
    svg.appendChild(label);
}

function drawCurrentTimeArrow(svg) {
    const now = new Date();

    const sec =
        now.getHours() * 3600 +
        now.getMinutes() * 60 +
        now.getSeconds();

    const cx = 150;
    const cy = 150;
    const angle = secToAngle(sec);

    // черта пересекает кольцо: от внутреннего края к внешнему
    const p1 = polarToXY(cx, cy, 62, angle);
    const p2 = polarToXY(cx, cy, 104, angle);

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', p1.x);
    line.setAttribute('y1', p1.y);
    line.setAttribute('x2', p2.x);
    line.setAttribute('y2', p2.y);
    line.setAttribute('stroke', '#334155');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-linecap', 'round');
    svg.appendChild(line);

    const labelPoint = polarToXY(cx, cy, 48, angle - 12);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', labelPoint.x);
    label.setAttribute('y', labelPoint.y);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '11');
    label.setAttribute('font-weight', '700');
    label.setAttribute('fill', '#111827');
    label.textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    svg.appendChild(label);
}

function hhmmToSeconds(value) {
    const parts = String(value || '00:00').split(':');
    const h = parseInt(parts[0] || '0', 10);
    const m = parseInt(parts[1] || '0', 10);
    return h * 3600 + m * 60;
}

function secToAngle(sec) {
    return (sec / 86400) * 360 - 90;
}

function polarToXY(cx, cy, r, angleDeg) {
    const rad = angleDeg * Math.PI / 180;
    return {
        x: cx + r * Math.cos(rad),
        y: cy + r * Math.sin(rad)
    };
}

function showToast(message, type = 'success', duration = 2500) {
    const container = document.getElementById('toast-container');

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // анимация появления
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // удаление
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function updateToastOffset() {
    const header = document.querySelector('nav');
    const container = document.getElementById('toast-container');

    if (!header || !container) return;

    const rect = header.getBoundingClientRect();
    container.style.top = (rect.height + 12) + 'px';
}

function duplicateCycle() {
    if (!currentCycle) {
        showToast('Нет цикла для копирования', 'error');
        return;
    }

    // создаём копию
    const copy = JSON.parse(JSON.stringify(currentCycle));

    copy.id = null;
    copy.name = copy.name + ' (копия)';

    currentCycle = copy;
    currentSteps = JSON.parse(JSON.stringify(copy.steps || []));

    document.getElementById('editor-title').innerText = 'Копия цикла';
    document.getElementById('cycle-id').value = '';
    document.getElementById('cycle-name').value = copy.name;
    document.getElementById('cycle-type').value = copy.cycle_type;
    document.getElementById('cycle-enabled').value = copy.enabled ? '1' : '0';
    document.getElementById('cycle-first-time').value = copy.first_time;

    setPeriodInputs(copy.period_minutes);

    renderSteps();
    updatePreview();
    setDirty(true);

    showToast('Цикл скопирован');
}

function drawTimeLabelAtAngle(svg, text, angleDeg, radius) {
    const cx = 150;
    const cy = 150;

    const angle = angleDeg - 90;
    const p = polarToXY(cx, cy, radius, angle);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', p.x);
    label.setAttribute('y', p.y);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dominant-baseline', 'middle');
    label.setAttribute('font-size', '13');
    label.setAttribute('fill', '#374151');

    label.textContent = text;
    svg.appendChild(label);
}

window.addEventListener('load', updateToastOffset);
window.addEventListener('resize', updateToastOffset);
document.addEventListener('DOMContentLoaded', loadConstructorData);