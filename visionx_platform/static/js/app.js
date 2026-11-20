const $ = (id) => document.getElementById(id);
const state = { uploadedFilename: null, pollTimer: null, chart: null, toastTimer: null };

function showToast(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove('show'), 3600);
}

async function postJSON(url, body = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.message || `Request failed (${response.status})`);
  return data;
}

function setFeedRunning(running) {
  $('cameraBtn').disabled = running;
  $('stopBtn').disabled = !running;
  $('topStatus').textContent = running ? 'SYSTEM ACTIVE' : 'SYSTEM IDLE';
  $('engineBadge').textContent = running ? 'ACTIVE' : 'IDLE';
  $('engineBadge').classList.toggle('on', running);
  $('trackingState').textContent = running ? 'Active' : 'Standby';
  document.querySelector('.tracking-foot').classList.toggle('active', running);
  $('feedDot').classList.toggle('active', running);
  $('feedState').textContent = running ? 'CONNECTING' : 'OFFLINE';
  $('feedStatus')?.classList.toggle('active', running);
  if (running) {
    $('feedPlaceholder').hidden = true;
    $('videoFeed').hidden = false;
    $('videoFeed').src = `/video_feed?t=${Date.now()}`;
  }
}

async function startCamera() {
  $('actionMessage').textContent = 'Opening local camera…';
  try {
    const result = await postJSON('/api/camera/start', { camera_index: 0 });
    setFeedRunning(true);
    $('actionMessage').textContent = result.message;
    showToast('Camera source started. Initial model load may take a moment.');
    beginPolling();
  } catch (error) {
    $('actionMessage').textContent = error.message;
    showToast(error.message);
  }
}

async function uploadAndStart(file) {
  if (!file) return;
  const maxBytes = 500 * 1024 * 1024;
  if (file.size > maxBytes) {
    showToast('The selected file exceeds the 500 MB upload limit.');
    return;
  }
  $('actionMessage').textContent = 'Uploading video…';
  $('videoFile').disabled = true;
  try {
    const form = new FormData();
    form.append('video', file);
    const uploadResponse = await fetch('/api/video/upload', { method: 'POST', body: form });
    const uploaded = await uploadResponse.json();
    if (!uploadResponse.ok || !uploaded.ok) throw new Error(uploaded.message || 'Video upload failed.');
    state.uploadedFilename = uploaded.filename;
    const started = await postJSON('/api/video/start', { filename: uploaded.filename });
    setFeedRunning(true);
    $('sourceName').textContent = uploaded.original_name;
    $('actionMessage').textContent = `${uploaded.original_name} · ${uploaded.size_mb} MB`;
    showToast('Video uploaded. AI analysis started.');
    beginPolling();
  } catch (error) {
    $('actionMessage').textContent = error.message;
    showToast(error.message);
  } finally {
    $('videoFile').disabled = false;
    $('videoFile').value = '';
  }
}

async function stopProcessing() {
  try {
    await postJSON('/api/stop');
    setFeedRunning(false);
    $('videoFeed').hidden = true;
    $('feedPlaceholder').hidden = false;
    $('feedPlaceholder').querySelector('h3').textContent = 'Processing stopped';
    $('feedPlaceholder').querySelector('p').textContent = 'Connect a camera or upload another video to start a new session.';
    $('feedState').textContent = 'OFFLINE';
    $('actionMessage').textContent = 'Processing stopped.';
    showToast('Vision engine stopped.');
    if (state.pollTimer) clearInterval(state.pollTimer);
  } catch (error) {
    showToast(error.message);
  }
}

function beginPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  refreshStatus();
  state.pollTimer = setInterval(refreshStatus, 900);
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    const data = await response.json();
    updateDashboard(data);
  } catch (_error) {
    $('actionMessage').textContent = 'Unable to read engine status. Check that the local server is running.';
  }
}

function updateDashboard(data) {
  const running = Boolean(data.running);
  if (data.source) $('sourceName').textContent = data.source;
  if (data.state === 'running') {
    $('feedState').textContent = 'ONLINE';
    $('feedDot').classList.add('active');
  } else if (data.state === 'loading_model') {
    $('feedState').textContent = 'LOADING AI';
  } else if (data.state === 'error') {
    $('feedState').textContent = 'ERROR';
    $('actionMessage').textContent = data.message;
    showToast(data.message);
  } else if (!running) {
    $('feedState').textContent = 'OFFLINE';
  }
  $('fpsValue').innerHTML = `${Number(data.fps || 0).toFixed(1)} <small>FPS</small>`;
  $('latencyValue').innerHTML = `${data.processing_ms ? Number(data.processing_ms).toFixed(1) : '—'} <small>ms</small>`;
  $('fpsMeter').style.width = `${Math.min(100, (Number(data.fps || 0) / 60) * 100)}%`;
  $('peopleValue').textContent = data.people ?? 0;
  $('vehiclesValue').textContent = data.vehicles ?? 0;
  $('bicyclesValue').textContent = data.bicycles ?? 0;
  $('totalValue').textContent = data.detections ?? 0;
  $('peopleUnique').textContent = `${data.unique_people ?? 0} unique IDs`;
  $('vehiclesUnique').textContent = `${data.unique_vehicles ?? 0} unique IDs`;
  $('bicyclesUnique').textContent = `${data.unique_bicycles ?? 0} unique IDs`;
  $('trackPeople').textContent = data.unique_people ?? 0;
  $('trackVehicles').textContent = data.unique_vehicles ?? 0;
  $('trackBicycles').textContent = data.unique_bicycles ?? 0;
  $('detectionsValue').textContent = data.detections ?? 0;
  $('trafficValue').textContent = (data.traffic || 'No data').toUpperCase();
  $('trafficValue').className = data.traffic === 'Heavy' ? 'traffic-heavy' : data.traffic === 'Moderate' ? 'traffic-moderate' : '';
  const density = data.traffic === 'Heavy' ? 100 : data.traffic === 'Moderate' ? 62 : data.traffic === 'Light' ? 27 : 0;
  $('densityFill').style.width = `${density}%`;
  $('analysisMessage').textContent = running ? `${data.detections || 0} target object(s) visible in the latest frame.` : (data.message || 'Start a feed to calculate scene activity.');
  $('engineBadge').textContent = data.state === 'loading_model' ? 'LOADING' : data.state === 'error' ? 'ERROR' : running ? 'ACTIVE' : 'IDLE';
  $('engineBadge').classList.toggle('on', running);
  $('trackingState').textContent = data.state === 'loading_model' ? 'Loading' : running ? 'Active' : 'Standby';
  document.querySelector('.tracking-foot').classList.toggle('active', running);
  $('topStatus').textContent = running ? 'SYSTEM ACTIVE' : data.state === 'error' ? 'SYSTEM ERROR' : 'SYSTEM IDLE';
  if (data.history?.length) {
    $('chartEmpty').hidden = true;
    updateChart(data.history);
  }
  if (!running && data.state === 'error') {
    $('cameraBtn').disabled = false;
    $('stopBtn').disabled = true;
  }
  if (!running && data.state === 'stopped' && state.pollTimer) {
    // Keep polling only while a source was recently started; the video can end naturally.
    if (data.message === 'Video ended') {
      $('feedPlaceholder').hidden = false;
      $('videoFeed').hidden = true;
      $('feedPlaceholder').querySelector('h3').textContent = 'Video analysis complete';
      $('feedPlaceholder').querySelector('p').textContent = 'The uploaded video reached its end. Start another source to continue.';
      $('cameraBtn').disabled = false;
      $('stopBtn').disabled = true;
    }
  }
}

function updateChart(history) {
  const labels = history.map((point) => point.time);
  const datasets = [
    { label: 'People', data: history.map(p => p.people), borderColor: '#27d9ef', backgroundColor: 'rgba(39,217,239,.08)', tension: .35, pointRadius: 0, borderWidth: 2 },
    { label: 'Vehicles', data: history.map(p => p.vehicles), borderColor: '#ff9b37', backgroundColor: 'rgba(255,155,55,.06)', tension: .35, pointRadius: 0, borderWidth: 2 },
    { label: 'Bicycles', data: history.map(p => p.bicycles), borderColor: '#a77bff', backgroundColor: 'rgba(167,123,255,.05)', tension: .35, pointRadius: 0, borderWidth: 2 }
  ];
  if (!state.chart) {
    const ctx = $('activityChart').getContext('2d');
    state.chart = new Chart(ctx, {
      type: 'line', data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false, backgroundColor: '#102334', titleColor: '#dcecf5', bodyColor: '#a8bfce', borderColor: '#28506a', borderWidth: 1 } },
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { grid: { color: 'rgba(70,105,126,.12)' }, ticks: { color: '#71899c', maxTicksLimit: 7, font: { size: 9 } }, border: { color: '#243a4b' } },
          y: { beginAtZero: true, suggestedMax: 4, grid: { color: 'rgba(70,105,126,.15)' }, ticks: { color: '#71899c', precision: 0, font: { size: 9 } }, border: { color: '#243a4b' } }
        }
      }
    });
  } else {
    state.chart.data.labels = labels;
    state.chart.data.datasets.forEach((dataset, index) => dataset.data = datasets[index].data);
    state.chart.update('none');
  }
}

$('cameraBtn').addEventListener('click', startCamera);
$('stopBtn').addEventListener('click', stopProcessing);
$('videoFile').addEventListener('change', (event) => uploadAndStart(event.target.files[0]));

// Read the server state on initial page load (the processor remains local to this server).
refreshStatus();
