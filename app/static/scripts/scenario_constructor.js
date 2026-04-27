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

document.addEventListener('DOMContentLoaded', loadConstructorData);