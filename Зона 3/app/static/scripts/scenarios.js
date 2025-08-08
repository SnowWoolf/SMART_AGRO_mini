function openAddScenarioModal(type) {
    document.getElementById('scenario-type').value = type;
    const parameterSelect = document.getElementById('scenario-parameter');
    const valueSelect = document.getElementById('scenario-value');
    const valueNumber = document.getElementById('scenario-value-number');
    parameterSelect.innerHTML = ''; // Очищаем список параметров
    valueSelect.style.display = 'block';
    valueNumber.style.display = 'none';

    const polivParameters = [
    'Клапан 1.1',  'Клапан 1.2',  'Клапан 1.3',  'Клапан 1.4',  'Клапан 1.5',
    'Клапан 1.6',  'Клапан 1.7',  'Клапан 1.8',  'Клапан 1.9',  'Клапан 1.10',
    'Клапан 2.1',  'Клапан 2.2',  'Клапан 2.3',  'Клапан 2.4',  'Клапан 2.5',
    'Клапан 2.6',  'Клапан 2.7',  'Клапан 2.8',  'Клапан 2.9',  'Клапан 2.10',
    'Клапан перемешивания', 'Наполнение бака', 'Слив с бака', 'Насос', 'Растворный узел'
];

    // 2. Все каналы (Линия X этаж Y ЦВЕТ)
    const svetParameters = [
        'КАНАЛ Линия 1 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 1 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 1 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 1 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 2 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 2 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 2 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 2 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 3 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 3 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 3 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 3 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 4 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 4 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 4 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 4 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 5 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 5 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 5 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 5 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 6 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 6 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 6 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 6 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 7 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 7 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 7 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 7 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 8 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 8 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 8 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 8 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 9 этаж 1 БЕЛЫЙ',   'КАНАЛ Линия 9 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 9 этаж 2 БЕЛЫЙ',   'КАНАЛ Линия 9 этаж 2 КРАСНЫЙ',

        'КАНАЛ Линия 10 этаж 1 БЕЛЫЙ',  'КАНАЛ Линия 10 этаж 1 КРАСНЫЙ',
        'КАНАЛ Линия 10 этаж 2 БЕЛЫЙ',  'КАНАЛ Линия 10 этаж 2 КРАСНЫЙ',
        'Освещение 1 этаж', 'Освещение 2 этаж'
    ];

    const levelParameters = [
          'ЯРКОСТЬ Линия 1 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 1 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 1 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 1 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 2 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 2 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 2 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 2 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 3 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 3 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 3 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 3 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 4 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 4 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 4 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 4 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 5 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 5 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 5 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 5 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 6 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 6 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 6 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 6 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 7 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 7 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 7 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 7 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 8 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 8 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 8 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 8 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 9 этаж 1 БЕЛЫЙ',   'ЯРКОСТЬ Линия 9 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 9 этаж 2 БЕЛЫЙ',   'ЯРКОСТЬ Линия 9 этаж 2 КРАСНЫЙ',

          'ЯРКОСТЬ Линия 10 этаж 1 БЕЛЫЙ',  'ЯРКОСТЬ Линия 10 этаж 1 КРАСНЫЙ',
          'ЯРКОСТЬ Линия 10 этаж 2 БЕЛЫЙ',  'ЯРКОСТЬ Линия 10 этаж 2 КРАСНЫЙ'
        ];

    const parameters = type === 'Полив' ? polivParameters : svetParameters.concat(levelParameters);

    parameters.forEach(param => {
        const option = document.createElement('option');
        option.value = param;
        option.text = param;
        parameterSelect.add(option);
    });

    parameterSelect.addEventListener('change', () => {
        if (levelParameters.includes(parameterSelect.value)) {
            valueSelect.style.display = 'none';
            valueNumber.style.display = 'block';
        } else {
            valueSelect.style.display = 'block';
            valueNumber.style.display = 'none';
        }
    });

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

    // Проверяем, какое значение использовать
    if (document.getElementById('scenario-value-number').style.display === 'block') {
        data['value'] = document.getElementById('scenario-value-number').value;
    }

    console.log('Form data to send:', data);  // Вывод данных формы в консоль

    fetch('/add_scenario', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        console.log('Server response:', result);  // Вывод ответа сервера в консоль
        if (result.success) {
            closeModal();
            location.reload(); // Обновляем страницу для отображения новых данных
        } else {
            alert('Error adding scenario: ' + result.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);  // Вывод ошибки в консоль
    });
}


function deleteScenario(id, type) {
    fetch('/delete_scenario', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ id: id })
    })
    .then(response => response.json())
    .then(result => {
        location.reload(); // Обновляем страницу для отображения новых данных
    })
    .catch(error => {
        console.error('Error:', error);  // Вывод ошибки в консоль
    });
}
