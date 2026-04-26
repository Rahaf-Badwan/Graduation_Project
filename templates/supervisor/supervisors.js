const titles={dashboard:'DashBoard',mystudents:'Students & Projects',progress:'Progress',feedback:'Feedback',evaluation:'Evaluation Projects',search:'Search & Filtering',notifs:'Notifications',ai:'ChatBoot',profile:'My profile'};
function go(id,el){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('on'));
  document.getElementById('pg-'+id)?.classList.add('on');
  document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('on'));
  if(el)el.classList.add('on');
  document.getElementById('tb-title').textContent=titles[id]||'';
}
function askAI(){
  const inp=document.getElementById('chatIn');
  if(!inp?.value.trim())return;
  sendPrompt(' Qustion fot chatBoot from the supervisor : '+inp.value+' ↗');
  inp.value='';
}
function setQ(q){const inp=document.getElementById('chatIn');if(inp){inp.value=q;inp.focus();}}
document.getElementById('chatIn')?.addEventListener('keydown',e=>{if(e.key==='Enter')askAI()});