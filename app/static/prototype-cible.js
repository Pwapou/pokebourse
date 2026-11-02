const viewNames={accueil:'Accueil',opportunites:'Opportunités',achats:'Mes achats',reglages:'Réglages'};
const sidebar=document.querySelector('#sidebar');
const toast=document.querySelector('#toast');
let toastTimer;
function notify(message){toast.textContent=message;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.hidden=true,4200)}
function showView(name){if(!viewNames[name])return;document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===`view-${name}`));document.querySelectorAll('.nav-link[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));document.querySelector('#current-view').textContent=viewNames[name];history.replaceState(null,'',`#${name}`);sidebar.classList.remove('open');window.scrollTo({top:0,behavior:'smooth'})}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.go)));
document.querySelectorAll('[data-view-link]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();showView(a.dataset.viewLink)}));
document.querySelector('#menu-button').addEventListener('click',()=>sidebar.classList.toggle('open'));
const advancedToggle=document.querySelector('#advanced-toggle');
const advancedNav=document.querySelector('#advanced-nav');
function toggleAdvanced(force){const open=force??advancedNav.hidden;advancedNav.hidden=!open;advancedToggle.setAttribute('aria-expanded',String(open));sidebar.classList.add('open')}
advancedToggle.addEventListener('click',()=>toggleAdvanced());
document.querySelector('#open-advanced').addEventListener('click',()=>{toggleAdvanced(true);notify('Toutes les fonctions avancées restent accessibles ici.')});
const addButton=document.querySelector('#add-button');
const addMenu=document.querySelector('#add-menu');
addButton.addEventListener('click',()=>{addMenu.hidden=!addMenu.hidden;addButton.setAttribute('aria-expanded',String(!addMenu.hidden))});
document.addEventListener('click',e=>{if(!e.target.closest('.add-menu-wrap')){addMenu.hidden=true;addButton.setAttribute('aria-expanded','false')}});
document.querySelectorAll('[data-demo]').forEach(b=>b.addEventListener('click',()=>notify(b.dataset.demo)));
const details={dracaufeu:{name:'Dracaufeu',subtitle:'Set de Base · N° 4/102 · FR · NM',cost:'149,50 €',resale:'240,00 €',profit:'+52,30 €',roi:'35,0 %',status:'Opportunité estimée'},pikachu:{name:'Pikachu VMAX',subtitle:'Voltage Éclatant · N° 188/185 · FR',cost:'69,50 €',resale:'115,00 €',profit:'+24,10 €',roi:'34,7 %',status:'Opportunité estimée'},mewtwo:{name:'Mewtwo V',subtitle:'Extension à confirmer · État inconnu',cost:'31,00 €',resale:'—',profit:'—',roi:'—',status:'Données insuffisantes'}};
const drawer=document.querySelector('#drawer');
const backdrop=document.querySelector('#drawer-backdrop');
let previousFocus;
function openDetail(key){const d=details[key];previousFocus=document.activeElement;document.querySelector('#detail-title').textContent=d.name;document.querySelector('#detail-subtitle').textContent=d.subtitle;document.querySelector('#detail-cost').textContent=d.cost;document.querySelector('#detail-resale').textContent=d.resale;document.querySelector('#detail-profit').textContent=d.profit;document.querySelector('#detail-roi').textContent=d.roi;document.querySelector('#detail-status').textContent=d.status;drawer.hidden=false;backdrop.hidden=false;document.querySelector('#close-drawer').focus()}
function closeDetail(){drawer.hidden=true;backdrop.hidden=true;previousFocus?.focus()}
document.querySelectorAll('[data-detail]').forEach(b=>b.addEventListener('click',()=>openDetail(b.dataset.detail)));
document.querySelector('#close-drawer').addEventListener('click',closeDetail);
backdrop.addEventListener('click',closeDetail);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!drawer.hidden)closeDetail();addMenu.hidden=true;sidebar.classList.remove('open')}});
const initial=location.hash.slice(1);if(viewNames[initial])showView(initial);
