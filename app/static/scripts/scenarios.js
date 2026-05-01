// VERSION: 2.0.270426
let scenarioParamsCache = null;

async function getScenarioParams() {
    if (scenarioParamsCache) return scenarioParamsCache;
    const resp = await fetch('/scenario_parameters');
    if (!resp.ok) throw new Error('Не удалось получить список параметров');
    scenarioParamsCache = await resp.json(); // { poliv:[], svet:[], svet_level:[] }
    return scenarioParamsCache;
}

async function openAddScenarioModal(type) {
    document.getElementById('scenario-type').value = type;

    const parameterSelect = document.getElementById('scenario-parameter');
    const valueSelect = document.getElementById('scenario-value');
    const valueNumber = document.getElementById('scenario-value-number');

    parameterSelect.innerHTML = '';
    valueSelect.style.display = 'block';
    valueNumber.style.display = 'none';
    valueNumber.value = ''; // сброс

    const { poliv, svet, svet_level } = await getScenarioParams();

    // Для "Свет" показываем и каналы (вкл/выкл), и уровни (число)
    const parameters = (type === 'Полив')
        ? poliv
        : [...svet, ...svet_level];

    parameters.forEach(param => {
        const option = document.createElement('option');
        option.value = param;
        option.text = param;
        parameterSelect.add(option);
    });

    // Если выбран параметр из "Свет уровень" — показываем числовое поле
    const onParameterChange = () => {
        if (svet_level.includes(parameterSelect.value)) {
            valueSelect.style.display = 'none';
            valueNumber.style.display = 'block';
        } else {
            valueSelect.style.display = 'block';
            valueNumber.style.display = 'none';
        }
    };

    // Снимем старый обработчик, если он был
    parameterSelect.onchange = onParameterChange;

    // Сразу применим для первого пункта
    onParameterChange();

    document.getElementById('addScenarioModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('addScenarioModal').style.display = 'none';
}

function addScenario() {
    const form = document.getElementById('addScenarioForm');
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value;
    });

    // Если выбрана «яркость», берём числовое значение
    if (document.getElementById('scenario-value-number').style.display === 'block') {
        data['value'] = document.getElementById('scenario-value-number').value;
    }

    fetch('/add_scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(result => {
        if (result.success) {
            closeModal();
            location.reload();
        } else {
            alert('Error adding scenario: ' + result.error);
        }
    })
    .catch(err => console.error('Error:', err));
}

function deleteScenario(id, type) {
    fetch('/delete_scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    })
    .then(r => r.json())
    .then(() => location.reload())
    .catch(err => console.error('Error:', err));
}
