const money = value => value == null ? "Inconnu" : new Intl.NumberFormat("fr-FR", {style:"currency",currency:"EUR"}).format(value);
const signed = value => value == null ? "Inconnu" : `${value > 0 ? "+" : ""}${money(value)}`;
const listings = [
 {id:1,name:"Pikachu 025/165",set:"151 · FR · NM",seller:"CardTrader_59",buy:10,reference:25,fees:3.25,profit:11.75,roi:117.5,status:"opportunity",label:"Opportunité",note:"Référence basée sur 12 ventes conclues · 28 oct. 2026"},
 {id:2,name:"Dracaufeu 4/102",set:"Base Set · FR · LP",seller:"Collection82",buy:240,reference:270,fees:15.5,profit:14.5,roi:6,status:"review",label:"À examiner",note:"Estimation manuelle · à confirmer sur les dernières ventes"},
 {id:3,name:"Mewtwo 150/165",set:"151 · FR · NM",seller:"PokeShop33",buy:42,reference:68,fees:5.4,profit:20.6,roi:49,status:"opportunity",label:"Opportunité",note:"Médiane de 8 ventes conclues · 30 oct. 2026"},
 {id:4,name:"Ronflex 143/165",set:"151 · FR · État inconnu",seller:"Vendeur local",buy:15,reference:null,fees:null,profit:null,roi:null,status:"insufficient",label:"Données insuffisantes",note:"Aucune référence correspondant à cette carte et à son état"},
 {id:5,name:"Évoli 133/165",set:"151 · FR · NM",seller:"CardsMarket",buy:7.5,reference:16,fees:2.8,profit:5.7,roi:76,status:"opportunity",label:"Opportunité",note:"Référence basée sur 5 ventes conclues · 31 oct. 2026"}
];
const purchases = [
 {id:11,name:"Mew ex 205/165",set:"151 · PSA 9",date:"24 oct. 2026",buy:180,reference:235,status:"to_sell",label:"À vendre"},
 {id:12,name:"Pikachu 025/165",set:"151 · FR · NM",date:"19 oct. 2026",buy:10,reference:25,status:"listed",label:"En vente"},
 {id:13,name:"Dracaufeu 4/102",set:"Base Set · FR · LP",date:"12 oct. 2026",buy:220,reference:270,status:"to_sell",label:"À vendre"},
 {id:14,name:"Mewtwo 150/165",set:"151 · FR · NM",date:"8 oct. 2026",buy:38,reference:68,status:"to_sell",label:"À vendre"},
 {id:15,name:"Florizarre 003/165",set:"151 · FR · NM",date:"29 sept. 2026",buy:65,reference:82,status:"listed",label:"En vente"},
 {id:16,name:"Tortank 009/165",set:"151 · FR · NM",date:"21 sept. 2026",buy:72,reference:94,status:"to_sell",label:"À vendre"},
 {id:17,name:"Alakazam 065/165",set:"151 · FR · NM",date:"14 sept. 2026",buy:29.5,reference:45,status:"collection",label:"Collection"},
 {id:18,name:"Évoli 133/165",set:"151 · FR · NM",date:"2 sept. 2026",buy:8,reference:16,status:"to_sell",label:"À vendre"}
];
const statusClass = item => item.status;
const identity = item => `<div class="product-identity"><div class="card-thumb">${item.name[0]}</div><div class="product-name"><strong>${item.name}</strong><span>${item.set}</span></div></div>`;
function showView(name){
 document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${name}`));
 document.querySelectorAll(".nav-link").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
 document.getElementById("sidebar").classList.remove("open");
 window.scrollTo({top:0,behavior:"instant"});
 if(location.hash!==`#${name}`) history.replaceState(null,"",`#${name}`);
}
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
document.querySelectorAll("[data-go]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.go)));
document.querySelectorAll("[data-view-link]").forEach(a=>a.addEventListener("click",e=>{e.preventDefault();showView(a.dataset.viewLink)}));
document.getElementById("menu-button").addEventListener("click",()=>document.getElementById("sidebar").classList.toggle("open"));
function openDrawer(item,type="listing"){
 const profit = type==="purchase" ? item.reference-item.buy : item.profit;
 const roi = type==="purchase" ? profit/item.buy*100 : item.roi;
 document.getElementById("drawer-content").innerHTML=`<div class="drawer-head"><div><span class="status ${statusClass(item)}">${item.label}</span><h2>${item.name}</h2><p>${item.set}</p></div><button class="close-button" aria-label="Fermer">✕</button></div><div class="drawer-body"><div class="drawer-stats"><div class="drawer-stat"><span>${type==="purchase"?"PRIX PAYÉ":"COÛT D’ACHAT"}</span><strong>${money(item.buy)}</strong></div><div class="drawer-stat"><span>REVENTE ESTIMÉE</span><strong>${money(item.reference)}</strong></div><div class="drawer-stat"><span>GAIN NET ESTIMÉ</span><strong class="${profit>0?"positive":""}">${signed(profit)}</strong></div><div class="drawer-stat"><span>ROI ESTIMÉ</span><strong>${roi==null?"Inconnu":`${roi.toFixed(1).replace(".",",")} %`}</strong></div></div>${type==="listing"?`<h3>Détail du calcul</h3><div class="calculation"><div class="calc-line"><span>Prix de l’annonce</span><b>${money(item.buy)}</b></div><div class="calc-line"><span>Port aller</span><b>0,00 €</b></div><div class="calc-line"><span>Prix de revente estimé</span><b>${money(item.reference)}</b></div><div class="calc-line"><span>Frais de vente</span><b>${item.fees==null?"Inconnus":`− ${money(item.fees)}`}</b></div><div class="calc-line total"><span>Gain net estimé</span><b>${signed(item.profit)}</b></div></div>`:`<h3>Suivi de l’achat</h3><div class="calculation"><div class="calc-line"><span>Date d’achat</span><b>${item.date}</b></div><div class="calc-line"><span>Statut</span><b>${item.label}</b></div><div class="calc-line total"><span>Plus-value latente</span><b>${signed(profit)}</b></div></div>`}<div class="assumption"><strong>Hypothèse de prix</strong><br>${item.note||"Valeur de marché estimée. Ce montant ne représente pas une vente confirmée."}</div><div class="drawer-actions"><button class="button secondary" id="drawer-close">Fermer</button><button class="button primary" id="drawer-action">${type==="purchase"?"Modifier le statut":"Examiner l’annonce"}</button></div></div>`;
 document.getElementById("drawer").hidden=false;document.getElementById("drawer-backdrop").hidden=false;
 const close=()=>{document.getElementById("drawer").hidden=true;document.getElementById("drawer-backdrop").hidden=true};
 document.querySelector(".close-button").onclick=close;document.getElementById("drawer-close").onclick=close;document.getElementById("drawer-backdrop").onclick=close;
 document.getElementById("drawer-action").onclick=()=>{close();toast(type==="purchase"?"Statut modifié dans la maquette":"Annonce ajoutée à votre sélection")};
}
function renderDashboard(){document.getElementById("dashboard-opportunities").innerHTML=listings.filter(x=>x.status==="opportunity").map(item=>`<div class="compact-row" data-id="${item.id}">${identity(item)}<div><span class="cell-label">ACHAT</span><b class="cell-value">${money(item.buy)}</b></div><div><span class="cell-label">GAIN NET</span><b class="cell-value positive">${signed(item.profit)}</b></div><div class="optional"><span class="cell-label">ROI</span><b class="cell-value">${item.roi.toFixed(1).replace(".",",")} %</b></div><span class="status ${item.status}">${item.label}</span></div>`).join("");document.querySelectorAll(".compact-row").forEach(r=>r.onclick=()=>openDrawer(listings.find(x=>x.id===Number(r.dataset.id))))}
function renderPurchases(){
 const filter=document.querySelector("[data-purchase-filter].active").dataset.purchaseFilter;
 const sort=document.getElementById("purchase-sort").value;
 let rows=purchases.filter(x=>filter==="all"||x.status===filter);
 rows.sort((a,b)=>sort==="name"?a.name.localeCompare(b.name):sort==="profit"?(b.reference-b.buy)-(a.reference-a.buy):b.id-a.id);
 document.getElementById("purchase-list").innerHTML=rows.map(item=>`<div class="product-row" data-id="${item.id}" tabindex="0">${identity(item)}<div><span class="cell-label">DATE D’ACHAT</span><b class="cell-value">${item.date}</b></div><div><span class="cell-label">PRIX PAYÉ</span><b class="cell-value">${money(item.buy)}</b></div><div><span class="cell-label">VALEUR ESTIMÉE</span><b class="cell-value">${money(item.reference)}</b></div><div class="optional"><span class="cell-label">PLUS-VALUE</span><b class="cell-value positive">${signed(item.reference-item.buy)}</b></div><span class="status ${item.status}">${item.label}</span><button class="row-action" aria-label="Voir ${item.name}">›</button></div>`).join("");
 document.querySelectorAll("#purchase-list .product-row").forEach(r=>{const open=()=>openDrawer(purchases.find(x=>x.id===Number(r.dataset.id)),"purchase");r.onclick=open;r.onkeydown=e=>{if(e.key==="Enter")open()}})
}
document.querySelectorAll("[data-purchase-filter]").forEach(b=>b.onclick=()=>{document.querySelectorAll("[data-purchase-filter]").forEach(x=>x.classList.remove("active"));b.classList.add("active");renderPurchases()});
document.getElementById("purchase-sort").onchange=renderPurchases;
function renderListings(){
 const query=document.getElementById("listing-search").value.toLowerCase();const status=document.getElementById("listing-status").value;const sort=document.getElementById("listing-sort").value;
 let rows=listings.filter(x=>(status==="all"||x.status===status)&&(`${x.name} ${x.set} ${x.seller}`.toLowerCase().includes(query)));
 rows.sort((a,b)=>sort==="price"?a.buy-b.buy:sort==="roi"?(b.roi??-1)-(a.roi??-1):(b.profit??-Infinity)-(a.profit??-Infinity));
 document.getElementById("listing-count").textContent=`${rows.length} annonce${rows.length>1?"s":""} · estimation nette de frais`;
 document.getElementById("listing-list").innerHTML=rows.length?rows.map(item=>`<div class="product-row" data-id="${item.id}" tabindex="0">${identity(item)}<div><span class="cell-label">ACHAT</span><b class="cell-value">${money(item.buy)}</b></div><div><span class="cell-label">REVENTE ESTIMÉE</span><b class="cell-value">${money(item.reference)}</b></div><div><span class="cell-label">GAIN NET</span><b class="cell-value ${item.profit>0?"positive":""}">${signed(item.profit)}</b></div><div class="optional"><span class="cell-label">ROI</span><b class="cell-value">${item.roi==null?"Inconnu":`${item.roi.toFixed(1).replace(".",",")} %`}</b></div><span class="status ${item.status}">${item.label}</span><button class="row-action" aria-label="Analyser ${item.name}">›</button></div>`).join(""):`<div class="padded"><strong>Aucun résultat</strong><p class="muted">Modifiez la recherche ou réinitialisez les filtres.</p></div>`;
 document.querySelectorAll("#listing-list .product-row").forEach(r=>{const open=()=>openDrawer(listings.find(x=>x.id===Number(r.dataset.id)));r.onclick=open;r.onkeydown=e=>{if(e.key==="Enter")open()}})
}
document.getElementById("listing-search").oninput=renderListings;document.getElementById("listing-status").onchange=renderListings;document.getElementById("listing-sort").onchange=renderListings;document.getElementById("listing-filters").onreset=()=>setTimeout(renderListings);
function toast(message){const el=document.getElementById("toast");el.textContent=message;el.hidden=false;setTimeout(()=>el.hidden=true,2600)}
document.getElementById("import-demo").onclick=()=>showView("imports");document.getElementById("add-purchase").onclick=()=>toast("Formulaire d’achat prévu dans la version intégrée");
document.querySelector(".upload-zone input").onchange=e=>{const notice=document.getElementById("import-notice");notice.hidden=false;notice.textContent=e.target.files.length?`Fichier « ${e.target.files[0].name} » sélectionné. Import simulé uniquement.`:"Aucun fichier sélectionné."};
document.getElementById("global-search").oninput=e=>{if(e.target.value){showView("listings");document.getElementById("listing-search").value=e.target.value;renderListings()}};
document.getElementById("reference-list").innerHTML=[listings[0],listings[2],listings[1]].map(x=>`<div class="reference-row"><div><strong>${x.name}</strong><small>${x.set}</small></div><strong>${money(x.reference)}</strong><div><small>TYPE</small>Ventes conclues</div><div><small>OBSERVATION</small>${x.note.split("·").pop()}</div></div>`).join("");
renderDashboard();renderPurchases();renderListings();showView(location.hash.slice(1)||"dashboard");
