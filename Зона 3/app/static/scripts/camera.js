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

  function getCamName(cam){
    // 1) пробуем data-cam-name на контейнере
    const el = document.getElementById(`cam${cam}_preview`);
    const wrap = el && el.closest('.camera');
    if (wrap && wrap.dataset && wrap.dataset.camName) return wrap.dataset.camName;

    // 2) fallback: текст в .cam-header
    const hdr = wrap && wrap.querySelector('.cam-header');
    if (hdr && hdr.textContent) return hdr.textContent.trim();

    // 3) последнее средство
    return `cam${cam}`;
  }
  function fileSafe(s){
    return String(s).trim()
      .replace(/[\\/:*?"<>|]/g, '-')  // недопустимые -> '-'
      .replace(/\s+/g, '_');          // пробелы -> '_'
  }
  function dtToSlug(dtStr){
    if(!dtStr) return '';
    // 'YYYY-MM-DDTHH:MM[:SS]' -> 'YYYY-MM-DD_HH-MM'
    const base = dtStr.slice(0, 16);
    return base.replace('T','_').replace(/:/g,'-');
  }

  async function fetchLatestInfo(cam){
    const r = await fetch(withCam(camLatestInfoUrl, cam), { credentials: 'same-origin' });
    if(!r.ok) throw new Error('нет кадров');
    return await r.json(); // { filename, iso }
  }

  // отрисовать последний кадр и подготовить ссылку "скачать"
  async function showLatest(cam){
    const info = await fetchLatestInfo(cam);          // { iso, filename }
    const img  = document.getElementById(`cam${cam}_preview`);
    if (img) img.src = cacheBust(withCam(camLatestJpgUrl, cam)); // превью ок

    // Скачивание: ведём на image_at с iso-временем и задаём имя сами
    const a = document.getElementById(`cam${cam}_download`);
    if (a){
      const camName = fileSafe(getCamName(cam));
      const dtIso   = info.iso;              // 'YYYY-MM-DDTHH:MM:SS'
      const dtSlug  = dtToSlug(dtIso);       // 'YYYY-MM-DD_HH-MM'

      a.href     = cacheBust(withCam(camImageAtUrl + '?dt=' + encodeURIComponent(dtIso), cam));
      a.download = `${camName}_frame_${dtSlug}.jpg`;
      a.dataset.dt = dtIso;
    }
  }



  // показать ближайший к указанной дате
  async function showNearestTo(cam, dtLocalStr){
    const img = document.getElementById(`cam${cam}_preview`);
    const url = withCam(camImageAtUrl + '?dt=' + encodeURIComponent(dtLocalStr), cam);
    if (img) img.src = cacheBust(url);

    const a = document.getElementById(`cam${cam}_download`);
    if (a){
      const camName = fileSafe(getCamName(cam));
      const dtSlug  = dtToSlug(dtLocalStr);
      a.href     = cacheBust(url);
      a.download = `${camName}_frame_${dtSlug}.jpg`;
      a.dataset.dt = dtLocalStr;
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

      if (aDownload){
        aDownload.addEventListener('click', (ev)=>{
          // всегда принудительно ставим корректную ссылку и имя
          const dt = aDownload.dataset.dt;                     // то, что сохранили в шагах выше
          if (!dt) return;                                     // если по какой-то причине нет — пусть идёт как есть

          const camName = fileSafe(getCamName(cam));
          const dtSlug  = dtToSlug(dt);
          const url     = withCam(camImageAtUrl + '?dt=' + encodeURIComponent(dt), cam);

          aDownload.href     = cacheBust(url);
          aDownload.download = `${camName}_frame_${dtSlug}.jpg`;
          // ничего не предотвращаем — кликуем дальше
        });
      }

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
          if (dl){
            const camName = fileSafe(getCamName(cam));
            const dtSlug  = dtToSlug(dt);
            const url     = withCam(camImageAtUrl + '?dt=' + encodeURIComponent(dt), cam);
            dl.href     = cacheBust(url);
            dl.download = `${camName}_frame_${dtSlug}.jpg`;
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
        // === Лайтбокс: создаём один раз ===
    const lb = document.createElement('div');
    lb.id = 'imgLightbox';
    lb.innerHTML = '<img alt="просмотр">';
    document.body.appendChild(lb);
    const lbImg = lb.querySelector('img');

    function openLightbox(cam){
      // Предпочтительно — точный кадр по dt (оригинал), иначе текущий превью-URL
      const a   = document.getElementById(`cam${cam}_download`);
      const img = document.getElementById(`cam${cam}_preview`);
      let url = null;

      if (a && a.dataset.dt){
        url = withCam(camImageAtUrl + '?dt=' + encodeURIComponent(a.dataset.dt), cam);
      } else if (img && img.src){
        url = img.src;
      }
      if (!url) return;

      lbImg.src = cacheBust(url);
      lb.classList.add('open');
      document.body.classList.add('no-scroll');
    }

    // Клики по превью каждой камеры — открыть на весь экран
    cams.forEach(cam => {
      const img = document.getElementById(`cam${cam}_preview`);
      if (img){
        img.style.cursor = 'zoom-in';
        img.addEventListener('click', () => openLightbox(cam));
      }
    });

    // Закрытие: клик по фону или Esc
    lb.addEventListener('click', () => {
      lb.classList.remove('open');
      document.body.classList.remove('no-scroll');
      lbImg.src = '';
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && lb.classList.contains('open')) lb.click();
    });

  });
})();
