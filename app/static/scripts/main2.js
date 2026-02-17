// ============================
// нормализация
// ============================
const isOn = (v) => v === '1' || v === '1.0' || v === 1;

// ============================
// обновление кнопок
// ============================
async function updateData() {
    try {
        const response = await fetch(getParametersUrl);
        const data = await response.json();

        const updateButton = (id, key) => {
            const btn = document.getElementById(id);
            if (!btn) return;

            const on = isOn(data[key]);

            btn.classList.toggle('on', on);
            btn.classList.toggle('off', !on);
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
            btn.dataset.state = on ? 'on' : 'off';
        };

        updateButton('Rele_ch1', 'Канал 1');
        updateButton('Rele_ch2', 'Канал 2');
        updateButton('Rele_ch3', 'Канал 3');
        updateButton('Rele_ch4', 'Канал 4');
        updateButton('Rele_ch5', 'Канал 5');
        updateButton('Rele_ch6', 'Канал 6');

    } catch (e) {
        console.error("update error:", e);
    }
}

// ============================
// 🔴 ГЛОБАЛЬНЫЙ toggle
// ============================
window.toggleParameter = async function(parameterName) {
    try {
        console.log("CLICK →", parameterName);

        const response = await fetch(toggleParameterUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parameter: parameterName })
        });

        const r = await response.json();
        console.log("SERVER:", r);

        setTimeout(updateData, 150);

    } catch (e) {
        console.error("toggle error:", e);
    }
};

// ============================
// init
// ============================
document.addEventListener("DOMContentLoaded", () => {
    updateData();
    setInterval(updateData, 1000);
});
