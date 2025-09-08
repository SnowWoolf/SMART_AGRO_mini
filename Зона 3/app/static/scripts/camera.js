(function(){
  function cacheBust(url){
    const u = new URL(url, window.location.origin);
    u.searchParams.set('cb', Date.now());
    return u.toString();
  }

  async function fetchLatestInfo(){
    const r = await fetch(camLatestInfoUrl, { credentials: 'same-origin' });
    if(!r.ok) throw new Error('нет кадров');
    return await r.json(); // { filename, iso }
  }

  function setDtLocal(el, isoStr){
    const d = new Date(isoStr);
    const pad = n => String(n).padStart(2,'0');
    const v =
      d.getFullYear() + '-' +
      pad(d.getMonth()+1) + '-' +
      pad(d.getDate()) + 'T' +
      pad(d.getHours()) + ':' +
      pad(d.getMinutes());
    el.value = v;
  }

  async function showLatest(){
    const info = await fetchLatestInfo();
    const img = document.getElementById('cam_preview');
    img.src = cacheBust(camLatestJpgUrl);

    const dtInput = document.getElementById('cam_dtview');
    setDtLocal(dtInput, info.iso);

    const a = document.getElementById('cam_btn_download_current');
    a.href = cacheBust(camDownloadLatest);
    a.download = 'latest.jpg';
  }

  async function showNearestTo(dtLocalStr){
    const img = document.getElementById('cam_preview');
    img.src = cacheBust(camImageAtUrl + '?dt=' + encodeURIComponent(dtLocalStr));

    const a = document.getElementById('cam_btn_download_current');
    a.href = cacheBust(camDownloadAtUrl + '?dt=' + encodeURIComponent(dtLocalStr));
    a.download = 'frame_' + dtLocalStr.replace(/[:T]/g,'-') + '.jpg';
  }

  // Кнопки
  document.addEventListener('DOMContentLoaded', function(){
    const btnLatest = document.getElementById('cam_btn_latest');
    const btnFix = document.getElementById('cam_btn_fix');
    const dtview = document.getElementById('cam_dtview');
    const btnTl = document.getElementById('cam_btn_download_timelapse');

    if(btnLatest){
      btnLatest.addEventListener('click', async ()=>{
        try { await showLatest(); } catch(e){ alert('Не удалось загрузить последний кадр: '+ e.message); }
      });
    }

    if(btnFix){
      btnFix.addEventListener('click', async ()=>{
        btnFix.disabled = true; btnFix.textContent = 'Сохраняю...';
        try{
          const r = await fetch(camCaptureNowUrl, { method:'POST', credentials:'same-origin' });
          if(!r.ok) throw new Error('capture failed');
          await showLatest();
        }catch(e){
          alert('Не удалось зафиксировать кадр: ' + e.message);
        }finally{
          btnFix.disabled = false; btnFix.textContent = 'Зафиксировать текущий кадр';
        }
      });
    }

    if(dtview){
      dtview.addEventListener('change', async (e)=>{
        const v = e.target.value;
        if(!v) return;
        try { await showNearestTo(v); } catch(e){ alert('Не удалось показать кадр: ' + e.message); }
      });
    }

    if(btnTl){
      btnTl.addEventListener('click', (e)=>{
        e.preventDefault();
        const s = document.getElementById('cam_dtStart').value;
        const nd = document.getElementById('cam_dtEnd').value;
        const fps = document.getElementById('cam_fps').value || '20';
        if(!s || !nd){ alert('Укажите обе даты'); return; }
        const url = camTimelapseUrl + '?start=' + encodeURIComponent(s) + '&end=' + encodeURIComponent(nd) + '&fps=' + encodeURIComponent(fps) + '&dl=1';
        window.location.href = url;
      });
    }

    // Инициализация
    (async function init(){
      try { await showLatest(); } catch(e){ console.warn('Кадров пока нет:', e.message); }
    })();
  });
})();
