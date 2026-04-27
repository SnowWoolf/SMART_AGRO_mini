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

    if (constructorData.cycles.length > 0) {
        selectCycle(constructorData.cycles[0].id);
    } else {
        newCycle();
    }
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
            <td>${index + 1}</td>

            <td>
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

            <td>
                <select class="form-control" onchange="updateStepParameter(${index}, this.value)">
                    ${parameterOptions}
                </select>
            </td>

            <td>
                ${renderValueEditor(step, index)}
            </td>

           <td>
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
        alert(result.error || 'Ошибка сохранения');
        return;
    }

    await loadConstructorData();
	selectCycle(result.id);
	renderDayVisualization();
	setDirty(false);
	alert('Цикл успешно сохранен');
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

			if (eventSec < 86400) {
				result.push({
					time: secondsToHHMMSS(eventSec),
					stepIndex,
					parameter: step.parameter || '',
					value: step.value
				});
			}
		});

		return result;
	}
    while (startSec < 86400) {
        let offset = 0;

        steps.forEach((step, stepIndex) => {
            offset += parseInt(step.delay_sec || 0, 10);
            const eventSec = startSec + offset;

            if (eventSec < 86400) {
                result.push({
                    time: secondsToHHMMSS(eventSec),
                    stepIndex,
                    parameter: step.parameter || '',
                    value: step.value
                });
            }
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

    const duration = getCycleDurationSec(steps);
    if (duration <= 0) return [];

    const intervals = [];

    if (periodMin === 0) {
        intervals.push({
            start: firstSec,
            end: Math.min(firstSec + duration, 86400)
        });
        return intervals;
    }

    let start = firstSec;

    while (start < 86400) {
        intervals.push({
            start,
            end: Math.min(start + duration, 86400)
        });

        start += periodMin * 60;
    }

    return intervals;
}

function getCycleDurationSec(steps) {
    return steps.reduce((sum, step) => {
        return sum + parseInt(step.delay_sec || 0, 10);
    }, 0);
}

function drawDayBase(svg) {
    const cx = 130;
    const cy = 130;

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
    inner.setAttribute('r', 62);
    inner.setAttribute('fill', '#ffffff');
    svg.appendChild(inner);

    drawTimeLabel(svg, '00:00', 130, 32);
    drawTimeLabel(svg, '06:00', 225, 134);
    drawTimeLabel(svg, '12:00', 130, 238);
    drawTimeLabel(svg, '18:00', 35, 134);

    for (let h = 0; h < 24; h++) {
        const angle = secToAngle(h * 3600);
        const p1 = polarToXY(cx, cy, 96, angle);
        const p2 = polarToXY(cx, cy, h % 6 === 0 ? 106 : 101, angle);

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

    const cx = 130;
    const cy = 130;

    const radius = 82;
    const width = Math.max(5, 24 - layerIndex * 3);

    const startAngle = secToAngle(startSec);
    const endAngle = secToAngle(endSec);

    const path = describeArc(cx, cy, radius, startAngle, endAngle);

    const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    arc.setAttribute('d', path);
    arc.setAttribute('fill', 'none');
    arc.setAttribute('stroke', color);
    arc.setAttribute('stroke-width', width);
    arc.setAttribute('stroke-linecap', 'butt');
    arc.setAttribute('opacity', layerIndex === 0 ? '0.88' : '0.70');

    svg.appendChild(arc);
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

function describeArc(cx, cy, r, startAngle, endAngle) {
    const start = polarToXY(cx, cy, r, startAngle);
    const end = polarToXY(cx, cy, r, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    return [
        'M', start.x, start.y,
        'A', r, r, 0, largeArcFlag, 1, end.x, end.y
    ].join(' ');
}

document.addEventListener('DOMContentLoaded', loadConstructorData);