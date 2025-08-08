const buttonTexts = {
    'Клапан 1.1':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.2':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.3':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.4':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.5':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.6':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.7':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.8':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.9':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 1.10':          { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.1':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.2':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.3':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.4':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.5':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.6':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.7':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.8':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.9':           { on: 'Включен',   off: 'Выключен' },
    'Клапан 2.10':          { on: 'Включен',   off: 'Выключен' },
    'Клапан перемешивания': { on: 'Включен',   off: 'Выключен' },
    'Наполнение бака':      { on: 'Включен',   off: 'Выключен' },
    'Слив с бака':          { on: 'Включен',   off: 'Выключен' },
    'Насос':                { on: 'Включен',   off: 'Выключен' },
    'Освещение 1 этаж':     { on: 'Включен',   off: 'Выключен' },
    'Освещение 2 этаж':     { on: 'Включен',   off: 'Выключен' },
    'Режим эксплуатации': { on: 'Включен', off: 'Выключен' },
    'Растворный узел': { on: 'Включен', off: 'Выключен' },

    'КАНАЛ Линия 1 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 1 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 1 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 1 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 2 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 2 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 2 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 2 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 3 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 3 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 3 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 3 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 4 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 4 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 4 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 4 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 5 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 5 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 5 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 5 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 6 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 6 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 6 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 6 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 7 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 7 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 7 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 7 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 8 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 8 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 8 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 8 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 9 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 9 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 9 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 9 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

    'КАНАЛ Линия 10 этаж 1 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 10 этаж 1 КРАСНЫЙ':{ on: 'on', off: 'off' },
    'КАНАЛ Линия 10 этаж 2 БЕЛЫЙ':  { on: 'on', off: 'off' },
    'КАНАЛ Линия 10 этаж 2 КРАСНЫЙ':{ on: 'on', off: 'off' },

};

async function updateData() {
    try {
        const response = await fetch(getParametersUrl);
        const data = await response.json();

        const updateButton = (id, key) => {
            const btn = document.getElementById(id);
            if (btn) {
                const texts = buttonTexts[key] || { on: 'Включен', off: 'Выключен' };
                btn.textContent = data[key] === '1' ? texts.on : texts.off;
                btn.className = 'status-button ' + (data[key] === '1' ? 'on' : 'off');
            }
        };
        const updateButton2 = (id, key) => {
            const btn = document.getElementById(id);
            if (btn) {
                const texts = buttonTexts[key] || { on: 'Включен', off: 'Выключен' };
                btn.textContent = data[key] === '1' ? texts.on : texts.off;
                btn.className = 'btn ' + (data[key] === '1' ? 'on' : 'off');
            }
        };

        const updateText = (id, key) => {
            const elem = document.getElementById(id);
            if (!elem) return;

            const raw = data[key];
            const num = parseFloat(raw);
            if (!isNaN(num)) {
                // округляем до десятых
                elem.textContent = num.toFixed(0);
            } else {
                // не число — показываем как есть
                elem.textContent = raw;
            }
        };
        const updateText2 = (id, key) => {
            const elem = document.getElementById(id);
            if (!elem) return;

            const raw = data[key];
            const num = parseFloat(raw);
            if (!isNaN(num)) {
                // округляем до десятых
                elem.textContent = num.toFixed(1);
            } else {
                // не число — показываем как есть
                elem.textContent = raw;
            }
        };


        const updateStatusText = (id, key) => {
            const elem = document.getElementById(id);
            if (elem) {
                elem.textContent = data[key] === '1' ? 'вкл' : 'откл';
            }
        };

        const updateTimeText = (id, key) => {
            const elem = document.getElementById(id);
            if (elem) {
                const value = parseFloat(data[key]) || 0;
                elem.textContent = (value / 10).toFixed(0);
            }
        };

        // Новая функция для обновления графического индикатора в ячейке
        const updateBinaryIndicator = (id, key) => {
            const indicator = document.getElementById(id);
            if (indicator) {
                if (data[key] === '1.0') {
                    indicator.classList.remove('empty');
                    indicator.classList.add('filled');
                } else {
                    indicator.classList.remove('filled');
                    indicator.classList.add('empty');
                }
            }
        };
        updateButton('shelf1',  'Клапан 1.1');
        updateButton('shelf2',  'Клапан 1.2');
        updateButton('shelf3',  'Клапан 1.3');
        updateButton('shelf4',  'Клапан 1.4');
        updateButton('shelf5',  'Клапан 1.5');
        updateButton('shelf6',  'Клапан 1.6');
        updateButton('shelf7',  'Клапан 1.7');
        updateButton('shelf8',  'Клапан 1.8');
        updateButton('shelf9',  'Клапан 1.9');
        updateButton('shelf10', 'Клапан 1.10');

        updateButton('shelf11', 'Клапан 2.1');
        updateButton('shelf12', 'Клапан 2.2');
        updateButton('shelf13', 'Клапан 2.3');
        updateButton('shelf14', 'Клапан 2.4');
        updateButton('shelf15', 'Клапан 2.5');
        updateButton('shelf16', 'Клапан 2.6');
        updateButton('shelf17', 'Клапан 2.7');
        updateButton('shelf18', 'Клапан 2.8');
        updateButton('shelf19', 'Клапан 2.9');
        updateButton('shelf20', 'Клапан 2.10');

        updateButton('shelf21', 'Клапан перемешивания');

        updateButton('shelf25', 'Наполнение бака');
        updateButton('shelf26', 'Слив с бака');

        updateButton('shelf28', 'Насос');
        updateButton('shelf29', 'Освещение 1 этаж');
        updateButton('shelf30', 'Освещение 2 этаж');

        updateButton('mode_param', 'Режим эксплуатации');
        updateButton('mixing', 'Растворный узел');

        updateButton2('chanel_1_1_white', 'КАНАЛ Линия 1 этаж 1 БЕЛЫЙ');
        updateText('level_1_1_white',    'ЯРКОСТЬ Линия 1 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_1_1_red',   'КАНАЛ Линия 1 этаж 1 КРАСНЫЙ');
        updateText('level_1_1_red',      'ЯРКОСТЬ Линия 1 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_1_2_white', 'КАНАЛ Линия 1 этаж 2 БЕЛЫЙ');
        updateText('level_1_2_white',    'ЯРКОСТЬ Линия 1 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_1_2_red',   'КАНАЛ Линия 1 этаж 2 КРАСНЫЙ');
        updateText('level_1_2_red',      'ЯРКОСТЬ Линия 1 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_2_1_white', 'КАНАЛ Линия 2 этаж 1 БЕЛЫЙ');
        updateText('level_2_1_white',    'ЯРКОСТЬ Линия 2 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_2_1_red',   'КАНАЛ Линия 2 этаж 1 КРАСНЫЙ');
        updateText('level_2_1_red',      'ЯРКОСТЬ Линия 2 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_2_2_white', 'КАНАЛ Линия 2 этаж 2 БЕЛЫЙ');
        updateText('level_2_2_white',    'ЯРКОСТЬ Линия 2 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_2_2_red',   'КАНАЛ Линия 2 этаж 2 КРАСНЫЙ');
        updateText('level_2_2_red',      'ЯРКОСТЬ Линия 2 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_3_1_white', 'КАНАЛ Линия 3 этаж 1 БЕЛЫЙ');
        updateText('level_3_1_white',    'ЯРКОСТЬ Линия 3 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_3_1_red',   'КАНАЛ Линия 3 этаж 1 КРАСНЫЙ');
        updateText('level_3_1_red',      'ЯРКОСТЬ Линия 3 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_3_2_white', 'КАНАЛ Линия 3 этаж 2 БЕЛЫЙ');
        updateText('level_3_2_white',    'ЯРКОСТЬ Линия 3 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_3_2_red',   'КАНАЛ Линия 3 этаж 2 КРАСНЫЙ');
        updateText('level_3_2_red',      'ЯРКОСТЬ Линия 3 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_4_1_white', 'КАНАЛ Линия 4 этаж 1 БЕЛЫЙ');
        updateText('level_4_1_white',    'ЯРКОСТЬ Линия 4 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_4_1_red',   'КАНАЛ Линия 4 этаж 1 КРАСНЫЙ');
        updateText('level_4_1_red',      'ЯРКОСТЬ Линия 4 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_4_2_white', 'КАНАЛ Линия 4 этаж 2 БЕЛЫЙ');
        updateText('level_4_2_white',    'ЯРКОСТЬ Линия 4 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_4_2_red',   'КАНАЛ Линия 4 этаж 2 КРАСНЫЙ');
        updateText('level_4_2_red',      'ЯРКОСТЬ Линия 4 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_5_1_white', 'КАНАЛ Линия 5 этаж 1 БЕЛЫЙ');
        updateText('level_5_1_white',    'ЯРКОСТЬ Линия 5 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_5_1_red',   'КАНАЛ Линия 5 этаж 1 КРАСНЫЙ');
        updateText('level_5_1_red',      'ЯРКОСТЬ Линия 5 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_5_2_white', 'КАНАЛ Линия 5 этаж 2 БЕЛЫЙ');
        updateText('level_5_2_white',    'ЯРКОСТЬ Линия 5 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_5_2_red',   'КАНАЛ Линия 5 этаж 2 КРАСНЫЙ');
        updateText('level_5_2_red',      'ЯРКОСТЬ Линия 5 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_6_1_white', 'КАНАЛ Линия 6 этаж 1 БЕЛЫЙ');
        updateText('level_6_1_white',    'ЯРКОСТЬ Линия 6 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_6_1_red',   'КАНАЛ Линия 6 этаж 1 КРАСНЫЙ');
        updateText('level_6_1_red',      'ЯРКОСТЬ Линия 6 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_6_2_white', 'КАНАЛ Линия 6 этаж 2 БЕЛЫЙ');
        updateText('level_6_2_white',    'ЯРКОСТЬ Линия 6 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_6_2_red',   'КАНАЛ Линия 6 этаж 2 КРАСНЫЙ');
        updateText('level_6_2_red',      'ЯРКОСТЬ Линия 6 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_7_1_white', 'КАНАЛ Линия 7 этаж 1 БЕЛЫЙ');
        updateText('level_7_1_white',    'ЯРКОСТЬ Линия 7 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_7_1_red',   'КАНАЛ Линия 7 этаж 1 КРАСНЫЙ');
        updateText('level_7_1_red',      'ЯРКОСТЬ Линия 7 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_7_2_white', 'КАНАЛ Линия 7 этаж 2 БЕЛЫЙ');
        updateText('level_7_2_white',    'ЯРКОСТЬ Линия 7 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_7_2_red',   'КАНАЛ Линия 7 этаж 2 КРАСНЫЙ');
        updateText('level_7_2_red',      'ЯРКОСТЬ Линия 7 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_8_1_white', 'КАНАЛ Линия 8 этаж 1 БЕЛЫЙ');
        updateText('level_8_1_white',    'ЯРКОСТЬ Линия 8 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_8_1_red',   'КАНАЛ Линия 8 этаж 1 КРАСНЫЙ');
        updateText('level_8_1_red',      'ЯРКОСТЬ Линия 8 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_8_2_white', 'КАНАЛ Линия 8 этаж 2 БЕЛЫЙ');
        updateText('level_8_2_white',    'ЯРКОСТЬ Линия 8 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_8_2_red',   'КАНАЛ Линия 8 этаж 2 КРАСНЫЙ');
        updateText('level_8_2_red',      'ЯРКОСТЬ Линия 8 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_9_1_white', 'КАНАЛ Линия 9 этаж 1 БЕЛЫЙ');
        updateText('level_9_1_white',    'ЯРКОСТЬ Линия 9 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_9_1_red',   'КАНАЛ Линия 9 этаж 1 КРАСНЫЙ');
        updateText('level_9_1_red',      'ЯРКОСТЬ Линия 9 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_9_2_white', 'КАНАЛ Линия 9 этаж 2 БЕЛЫЙ');
        updateText('level_9_2_white',    'ЯРКОСТЬ Линия 9 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_9_2_red',   'КАНАЛ Линия 9 этаж 2 КРАСНЫЙ');
        updateText('level_9_2_red',      'ЯРКОСТЬ Линия 9 этаж 2 КРАСНЫЙ');

        updateButton2('chanel_10_1_white', 'КАНАЛ Линия 10 этаж 1 БЕЛЫЙ');
        updateText('level_10_1_white',    'ЯРКОСТЬ Линия 10 этаж 1 БЕЛЫЙ');
        updateButton2('chanel_10_1_red',   'КАНАЛ Линия 10 этаж 1 КРАСНЫЙ');
        updateText('level_10_1_red',      'ЯРКОСТЬ Линия 10 этаж 1 КРАСНЫЙ');

        updateButton2('chanel_10_2_white', 'КАНАЛ Линия 10 этаж 2 БЕЛЫЙ');
        updateText('level_10_2_white',    'ЯРКОСТЬ Линия 10 этаж 2 БЕЛЫЙ');
        updateButton2('chanel_10_2_red',   'КАНАЛ Линия 10 этаж 2 КРАСНЫЙ');
        updateText('level_10_2_red',      'ЯРКОСТЬ Линия 10 этаж 2 КРАСНЫЙ');

        updateText2('UNIT_ID_PH', 'Уровень PH');
        updateText2('UNIT_ID_EC', 'Уровень EC');

        // Обновляем графические индикаторы для основного бака
        updateBinaryIndicator('indicator-level-1', 'Бак уровень 92%');
        updateBinaryIndicator('indicator-level-2', 'Бак уровень 75%');
        updateBinaryIndicator('indicator-level-3', 'Бак уровень 57%');
        updateBinaryIndicator('indicator-level-4', 'Бак уровень 40%');
        updateBinaryIndicator('indicator-level-5', 'Бак уровень 22%');
        updateBinaryIndicator('indicator-level-6', 'Бак уровень минимум 5%');

        // Обновляем графические индикаторы для баков компонентов
        updateBinaryIndicator('indicator-level-A', 'Середина компонент А');
        updateBinaryIndicator('indicator-level-A2', 'Минимум компонент А');
        updateBinaryIndicator('indicator-level-B', 'Середина компонент В');
        updateBinaryIndicator('indicator-level-B2', 'Минимум компонент В');
        updateBinaryIndicator('indicator-level-K', 'Середина кислота');
        updateBinaryIndicator('indicator-level-K2', 'Минимум кислота');

        updateStatusText('statusA', 'Подача A в бак');
        updateStatusText('statusB', 'Подача В в бак');
        updateStatusText('statusK', 'Подача кислоты в бак');
        updateTimeText('timeA', 'Время подачи A в бак');
        updateTimeText('timeB', 'Время подачи В в бак');
        updateTimeText('timeK', 'Время подачи кислоты в бак');

    } catch (error) {
        console.error("Ошибка обновления данных:", error);
    }
}

async function toggleParameter(parameterName) {
    try {
        const response = await fetch(toggleParameterUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parameter: parameterName })
        });
        await response.json();
        updateData();
    } catch (error) {
        console.error("Ошибка переключения параметра:", error);
    }
}

async function setValue() {
    const parameterName = document.getElementById('parameter-name').value;
    const parameterValue = document.getElementById('parameter-value').value;
    try {
        const response = await fetch(setParameterValueUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parameter: parameterName, value: parameterValue })
        });
        await response.json();
        closeModal();
        updateData();
    } catch (error) {
        console.error("Ошибка установки значения:", error);
    }
}

function openModal(parameterName) {
    document.getElementById('parameter-name').value = parameterName;
    document.getElementById('parameter-value').value = '';
    document.getElementById('valueModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('valueModal').style.display = 'none';
}

window.onclick = function(event) {
    const modal = document.getElementById('valueModal');
    if (event.target === modal) {
        closeModal();
    }
};

const brightnessInput = document.getElementById('parameter-value');
if (brightnessInput) {
    brightnessInput.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            setValue();
        }
    });
}

setInterval(updateData, 1000);
