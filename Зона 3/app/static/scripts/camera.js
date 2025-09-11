(function(){
  const withCam = (url, cam) => {
    const u = new URL(url, window.location.origin);
    u.searchParams.set('cam', String(cam));
    return u.toString();
  };
  const cacheBust = (url) => {
    const u = new URL(url, window.location.origin);
    u.searchParams.set('cb', Date.now());
    return u.toString();
  };

  async function fetchLatestInfo(cam){
    const r = await fetch(withCam(camLatestInfoUrl, cam), { credentials: 'same-origin' });
    if(!r.ok) throw new Error('нет кадров');
    return await r.json(); // { filename, iso }
  }

  // отрисовать последний кадр и подготовить ссылку "скачать"
  async function showLatest(cam){
    const info = await fetchLatestInfo(cam);
    const img = document.getElementById(`cam${cam}_preview`);
    if(img) img.src = cacheBust(withCam(camLatestJpgUrl, cam));

    const a = document.getElementById(`cam${cam}_download`);
    if(a){
      a.href = cacheBust(withCam(camDownloadLatest, cam));
      a.download = `cam${cam}_latest.jpg`;
    }
    // опционально можешь где-то показывать info.iso
  }

  // показать ближайший к указанной дате
  async function showNearestTo(cam, dtLocalStr){
    const img = document.getElementById(`cam${cam}_preview`);
    const imgUrl = withCam(camImageAtUrl + '?dt=' + encodeURIComponent(dtLocalStr), cam);
    if(img) img.src = cacheBust(imgUrl);

    const a = document.getElementById(`cam${cam}_download`);
    if(a){
      const dlUrl = withCam(camDownloadAtUrl + '?dt=' + encodeURIComponent(dtLocalStr), cam);
      a.href = cacheBust(dlUrl);
      a.download = `cam${cam}_frame_${dtLocalStr.replace(/[:T]/g,'-')}.jpg`;
    }
  }

  async function captureNow(cam, btn){
    try{
      if(btn){ btn.disabled = true; }
      const r = await fetch(withCam(camCaptureNowUrl, cam), { method:'POST', credentials:'same-origin' });
      if(!r.ok) throw new Error('capture failed');
      await showLatest(cam);
    } finally {
      if(btn){ btn.disabled = false; }
    }
  }

  // Timelapse — формируем ссылку и просто навигируем (скачивание)
  function saveTimelapse(cam, start, end, fps){
    if(!start || !end){ alert('Укажите обе даты'); return; }
    const url = withCam(
      camTimelapseUrl + '?start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end) + '&fps=' + encodeURIComponent(fps) + '&dl=1',
      cam
    );
    window.location.href = url;
  }

  document.addEventListener('DOMContentLoaded', function(){
    // перечислим камеры, которые реально присутствуют в DOM
    const cams = [1,2,3,4].filter(n => document.getElementById(`cam${n}_preview`));

    // бинды
    cams.forEach(cam => {
      const btnRefresh   = document.getElementById(`cam${cam}_refresh`);
      const btnCapture   = document.getElementById(`cam${cam}_capture`);
      const aDownload    = document.getElementById(`cam${cam}_download`);
      const btnHistory   = document.getElementById(`cam${cam}_history`);
      const btnTimelapse = document.getElementById(`cam${cam}_timelapse`);

      if(btnRefresh){
        btnRefresh.addEventListener('click', async ()=>{
          try{ await showLatest(cam); }catch(e){ alert(`Камера ${cam}: не удалось загрузить последний кадр: ` + e.message); }
        });
      }
      if(btnCapture){
        btnCapture.addEventListener('click', async ()=>{
          try{ await captureNow(cam, btnCapture); }catch(e){ alert(`Камера ${cam}: не удалось сделать снимок: ` + e.message); }
        });
      }
      // download (a) — ссылка устанавливается внутри showLatest() / showNearestTo()

      if(btnHistory){
        btnHistory.addEventListener('click', ()=>{
          // открыть общий модал истории
          document.getElementById('cam_frame_modal_camid').value = String(cam);
          document.getElementById('cam_frame_dt').value = '';
          document.getElementById('camFrameModal').style.display = 'block';
        });
      }

      if(btnTimelapse){
        btnTimelapse.addEventListener('click', ()=>{
          // открыть общий модал timelapse
          document.getElementById('cam_tl_modal_camid').value = String(cam);
          document.getElementById('cam_tl_start').value = '';
          document.getElementById('cam_tl_end').value = '';
          document.getElementById('cam_tl_fps').value = '20';
          document.getElementById('camTlModal').style.display = 'block';
        });
      }

      // первичная инициализация каждого превью
      (async()=>{ try{ await showLatest(cam); }catch(e){ console.warn(`Камера ${cam}: кадров пока нет`, e.message); }})();
    });

    // обработчики модалок (общие для всех камер)
    const frameShowBtn = document.getElementById('cam_frame_show');
    if(frameShowBtn){
      frameShowBtn.addEventListener('click', async ()=>{
        const cam = parseInt(document.getElementById('cam_frame_modal_camid').value, 10);
        const dt  = document.getElementById('cam_frame_dt').value;
        if(!dt){ alert('Укажите дату/время'); return; }
        try{
          await showNearestTo(cam, dt);
          // линк "Скачать" в модалке на тот же кадр
          const dl = document.getElementById('cam_frame_download');
          if(dl){
            dl.href = cacheBust(withCam(camDownloadAtUrl + '?dt=' + encodeURIComponent(dt), cam));
            dl.download = `cam${cam}_frame_${dt.replace(/[:T]/g,'-')}.jpg`;
          }
          document.getElementById('camFrameModal').style.display='none';
        }catch(e){
          alert('Не удалось показать кадр: ' + e.message);
        }
      });
    }

    const tlSaveBtn = document.getElementById('cam_tl_save');
    if(tlSaveBtn){
      tlSaveBtn.addEventListener('click', ()=>{
        const cam = parseInt(document.getElementById('cam_tl_modal_camid').value, 10);
        const s   = document.getElementById('cam_tl_start').value;
        const e   = document.getElementById('cam_tl_end').value;
        const fps = document.getElementById('cam_tl_fps').value || '20';
        saveTimelapse(cam, s, e, fps);
        document.getElementById('camTlModal').style.display='none';
      });
    }

    // закрытие модалок по клику вне
    window.addEventListener('click', (ev)=>{
      const m1 = document.getElementById('camFrameModal');
      const m2 = document.getElementById('camTlModal');
      if(ev.target === m1) m1.style.display='none';
      if(ev.target === m2) m2.style.display='none';
    });
  });
})();
