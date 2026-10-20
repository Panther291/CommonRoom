const loginView = document.querySelector('#login-view');
const browserView = document.querySelector('#browser-view');
const loginForm = document.querySelector('#login-form');
const loginError = document.querySelector('#login-error');
const passwordInput = document.querySelector('#password');
const listElement = document.querySelector('#file-list');
const breadcrumbElement = document.querySelector('#breadcrumbs');
const countElement = document.querySelector('#item-count');
const statusElement = document.querySelector('#status-message');
const searchInput = document.querySelector('#search');
const playerDialog = document.querySelector('#player');
const videoPlayer = document.querySelector('#video-player');
const audioPlayer = document.querySelector('#audio-player');

let currentPath = '';
let currentRoot = null;
let currentRootName = '';
let currentEntries = [];

function showLogin(message = '') {
  browserView.hidden = true;
  loginView.hidden = false;
  loginError.textContent = message;
  passwordInput.focus();
}

function showBrowser() {
  loginView.hidden = true;
  browserView.hidden = false;
  loadFolder('', null);
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  if (response.status === 401) {
    showLogin('Your session ended. Sign in again.');
    throw new Error('Sign in required');
  }
  return response;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes;
  let unit = -1;
  do { size /= 1024; unit += 1; } while (size >= 1024 && unit < units.length - 1);
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`;
}

function formatDate(timestamp) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(timestamp * 1000));
}

function iconForEntry(entry) {
  if (entry.volume) return 'drive';
  if (entry.directory) return 'folder';

  const extension = entry.name.includes('.') ? entry.name.split('.').pop().toLowerCase() : '';
  const type = entry.type || '';
  if (type.startsWith('video/') || ['3gp', 'mkv', 'mov', 'mp4', 'webm'].includes(extension)) return 'video';
  if (type.startsWith('image/') || ['avif', 'bmp', 'gif', 'heic', 'jpeg', 'jpg', 'png', 'svg', 'webp'].includes(extension)) return 'image';
  if (type.startsWith('audio/') || ['aac', 'flac', 'm4a', 'mp3', 'ogg', 'wav', 'wma'].includes(extension)) return 'audio';
  if (['7z', 'bz2', 'gz', 'rar', 'tar', 'xz', 'zip'].includes(extension)) return 'archive';
  if (['c', 'cc', 'cpp', 'css', 'go', 'h', 'hpp', 'html', 'java', 'js', 'json', 'py', 'rb', 'rs', 'ts', 'xml'].includes(extension)) return 'code';
  if (['csv', 'doc', 'docx', 'md', 'odt', 'pdf', 'ppt', 'pptx', 'rtf', 'txt', 'xls', 'xlsx'].includes(extension)) return 'document';
  return 'file';
}

function buildBreadcrumbs(path, root, rootName) {
  breadcrumbElement.replaceChildren();
  const parts = path ? path.split('/') : [];
  const crumbs = [{ label: 'Computer', path: '', root: null }];
  if (root) crumbs.push({ label: rootName, path: '', root });
  let joined = '';
  for (const part of parts) {
    joined = joined ? `${joined}/${part}` : part;
    crumbs.push({ label: part, path: joined, root });
  }
  crumbs.forEach((crumb, index) => {
    if (index) {
      const separator = document.createElement('span');
      separator.className = 'crumb-separator';
      separator.textContent = '/';
      breadcrumbElement.append(separator);
    }
    const button = document.createElement('button');
    button.className = 'crumb';
    button.type = 'button';
    button.textContent = crumb.label;
    button.addEventListener('click', () => loadFolder(crumb.path, crumb.root));
    breadcrumbElement.append(button);
  });
}

function fileUrl(path, inline = false) {
  const params = new URLSearchParams({ path, root: currentRoot || '' });
  if (inline) params.set('inline', '1');
  return `/api/file?${params.toString()}`;
}

function createEntry(entry, index) {
  const row = document.createElement('div');
  row.className = 'file-row';
  row.style.animationDelay = `${Math.min(index * 18, 180)}ms`;

  const main = document.createElement('div');
  main.className = 'file-main';
  const symbol = document.createElement('img');
  symbol.className = 'file-symbol';
  symbol.src = `/static/icons/${iconForEntry(entry)}.svg`;
  symbol.alt = '';
  symbol.setAttribute('aria-hidden', 'true');
  const name = entry.directory ? document.createElement('button') : document.createElement('span');
  name.className = entry.directory ? 'file-name folder-button' : 'file-name';
  name.textContent = entry.name;
  if (entry.directory) {
    name.type = 'button';
    name.addEventListener('click', () => loadFolder(entry.path, entry.root || currentRoot));
  }
  main.append(symbol, name);

  const detail = document.createElement('span');
  detail.className = 'file-detail';
  detail.textContent = entry.volume ? 'Drive' : entry.directory ? 'Folder' : formatSize(entry.size);
  const date = document.createElement('span');
  date.className = 'file-detail date-detail';
  date.textContent = entry.volume ? '' : formatDate(entry.modified);
  const actions = document.createElement('div');
  actions.className = 'file-actions';

  if (!entry.directory) {
    if (entry.type.startsWith('video/') || entry.type.startsWith('audio/')) {
      const play = document.createElement('button');
      play.className = 'text-action';
      play.type = 'button';
      play.textContent = 'Play';
      play.addEventListener('click', () => openPlayer(entry));
      actions.append(play);
    }
    const download = document.createElement('a');
    download.className = 'text-action';
    download.href = fileUrl(entry.path);
    download.textContent = 'Download';
    actions.append(download);
  }

  row.append(main, detail, date, actions);
  return row;
}

function renderEntries() {
  const filter = searchInput.value.trim().toLocaleLowerCase();
  const visible = currentEntries.filter((entry) => entry.name.toLocaleLowerCase().includes(filter));
  listElement.replaceChildren(...visible.map(createEntry));
  countElement.textContent = `${visible.length} ${visible.length === 1 ? 'ITEM' : 'ITEMS'}`;
  const emptyState = document.querySelector('#empty-state');
  emptyState.hidden = currentEntries.length !== 0;
  if (currentEntries.length === 0) {
    emptyState.querySelector('h2').textContent = currentRoot ? 'This folder is empty' : 'No drives found';
    emptyState.querySelector('p').textContent = currentRoot
      ? 'This folder does not contain any visible files.'
      : 'No mounted drives are available to browse.';
  }
  if (currentEntries.length && visible.length === 0) {
    countElement.textContent = '0 ITEMS';
    statusElement.textContent = 'No names match your search';
  } else {
    statusElement.textContent = '';
  }
}

async function loadFolder(path, root = currentRoot) {
  currentPath = path;
  currentRoot = root;
  searchInput.value = '';
  statusElement.textContent = 'Loading...';
  try {
    const query = new URLSearchParams({ path, root: currentRoot || '' });
    const response = await api(`/api/list?${query}`);
    if (!response.ok) throw new Error('Could not load this folder');
    const data = await response.json();
    currentEntries = data.entries;
    currentRoot = data.root || null;
    currentRootName = data.rootName;
    document.querySelector('#browser-title').textContent = currentRoot ? `Browse ${currentRootName}` : 'Your drives';
    buildBreadcrumbs(path, currentRoot, currentRootName);
    renderEntries();
  } catch (error) {
    if (error.message !== 'Sign in required') statusElement.textContent = error.message;
  }
}

function openPlayer(entry) {
  const isVideo = entry.type.startsWith('video/');
  videoPlayer.pause();
  audioPlayer.pause();
  videoPlayer.hidden = !isVideo;
  audioPlayer.hidden = isVideo;
  document.querySelector('#player-title').textContent = entry.name;
  const player = isVideo ? videoPlayer : audioPlayer;
  player.src = fileUrl(entry.path, true);
  player.load();
  playerDialog.showModal();
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.textContent = '';
  const submit = loginForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: passwordInput.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Sign-in failed');
    passwordInput.value = '';
    showBrowser();
  } catch (error) {
    loginError.textContent = error.message;
    passwordInput.select();
  } finally {
    submit.disabled = false;
  }
});

document.querySelector('#toggle-password').addEventListener('click', (event) => {
  const reveal = passwordInput.type === 'password';
  passwordInput.type = reveal ? 'text' : 'password';
  event.currentTarget.textContent = reveal ? 'Hide' : 'Show';
  event.currentTarget.setAttribute('aria-label', `${reveal ? 'Hide' : 'Show'} password`);
});

document.querySelector('#refresh').addEventListener('click', () => loadFolder(currentPath));
document.querySelector('#sign-out').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' });
  showLogin('');
});
document.querySelector('#close-player').addEventListener('click', () => playerDialog.close());
playerDialog.addEventListener('close', () => {
  videoPlayer.pause();
  audioPlayer.pause();
  videoPlayer.removeAttribute('src');
  audioPlayer.removeAttribute('src');
});
searchInput.addEventListener('input', renderEntries);

api('/api/session').then((response) => {
  if (response.ok) showBrowser();
  else showLogin();
}).catch(() => showLogin());