/**
 * offline-sync.js — SikaSkool offline-first module
 * 1. Détection réseau + bandeau UI
 * 2. Interception form offline → IndexedDB + reçu immédiat
 * 3. Sync auto au retour du réseau → POST /econome/sync/
 * Dépendance : matricule.js (chargé avant)
 */
(function () {
  'use strict';
  var DB_NAME='sukulu_offline', DB_VERSION=1, STORE='pending_payments', SYNC_URL='/econome/sync/';

  /* ── IndexedDB helpers ── */
  function openDB(){return new Promise(function(ok,ko){
    var r=indexedDB.open(DB_NAME,DB_VERSION);
    r.onupgradeneeded=function(e){var db=e.target.result;if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:'client_uuid'});};
    r.onsuccess=function(e){ok(e.target.result);}; r.onerror=function(e){ko(e.target.error);};
  });}
  function dbAdd(rec){return openDB().then(function(db){return new Promise(function(ok,ko){
    var tx=db.transaction(STORE,'readwrite'),r=tx.objectStore(STORE).put(rec);
    r.onsuccess=function(){ok();}; r.onerror=function(e){ko(e.target.error);};
  });});}
  function dbGetAll(){return openDB().then(function(db){return new Promise(function(ok,ko){
    var r=db.transaction(STORE,'readonly').objectStore(STORE).getAll();
    r.onsuccess=function(e){ok(e.target.result);}; r.onerror=function(e){ko(e.target.error);};
  });});}
  function dbDel(uuid){return openDB().then(function(db){return new Promise(function(ok,ko){
    var r=db.transaction(STORE,'readwrite').objectStore(STORE).delete(uuid);
    r.onsuccess=function(){ok();}; r.onerror=function(e){ko(e.target.error);};
  });});}
  function dbCount(){return openDB().then(function(db){return new Promise(function(ok){
    var r=db.transaction(STORE,'readonly').objectStore(STORE).count();
    r.onsuccess=function(e){ok(e.target.result);}; r.onerror=function(){ok(0);};
  });});}

  /* ── Bandeau réseau ── */
  var _b=null;
  function _banner(){if(_b)return _b;
    _b=document.createElement('div'); _b.id='offlineBanner';
    _b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;display:none;align-items:center;justify-content:center;gap:.6rem;padding:.55rem 1rem;font-size:.8125rem;font-weight:500;background:#1a1d29;color:#f0f1f5;border-bottom:1px solid rgba(255,255,255,.08);box-shadow:0 2px 8px rgba(0,0,0,.25);';
    _b.innerHTML='<svg style="width:.9rem;height:.9rem;stroke:#fbbf24;fill:none;stroke-width:2;stroke-linecap:round;flex-shrink:0" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><span id="_obTxt">Mode hors-ligne</span>';
    document.body.prepend(_b); return _b;}
  function showBanner(n){
    var b=_banner(); b.style.display='flex';
    b.querySelector('#_obTxt').textContent=n>0?'Mode hors-ligne \u2014 '+n+' encaissement(s) en attente.':'Mode hors-ligne \u2014 encaissements synchronis\u00e9s au retour du r\u00e9seau.';}
  function hideBanner(){if(_b)_b.style.display='none';}

  /* ── CSRF ── */
  function csrf(){var m=document.cookie.match(/csrftoken=([^;]+)/);return m?m[1]:'';}

  /* ── Sync ── */
  var _syncing=false;
  function syncAll(){
    if(_syncing||!navigator.onLine)return;
    dbGetAll().then(function(items){
      if(!items||!items.length)return;
      _syncing=true;
      fetch(SYNC_URL,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify({payments:items})})
      .then(function(r){return r.json();})
      .then(function(d){
        var synced=0,failed=0,ps=(d.results||[]).map(function(res){
          if(res.status==='synced'||res.status==='duplicate'){synced++;return dbDel(res.client_uuid);}
          failed++;return Promise.resolve();
        });
        return Promise.all(ps).then(function(){return dbCount().then(function(n){
          _syncing=false;
          if(n===0)hideBanner();else showBanner(n);
          var t=window.showToast;
          if(t&&synced)t(synced+' encaissement(s) synchronis\u00e9(s).','success');
          if(t&&failed)t(failed+' encaissement(s) en \u00e9chec.','error');
        });});
      })
      .catch(function(e){_syncing=false;console.warn('[Sukulu]',e);});
    });
  }

  /* ── Recu offline ── */
  function _row(l,v){
    return '<div style="display:flex;justify-content:space-between;align-items:baseline;">'
      +'<dt style="font-size:.8125rem;color:#9397a8;">'+l+'</dt>'
      +'<dd style="font-size:.8125rem;font-weight:600;">'+(v||'\u2014')+'</dd></div>';}
  function showOfflineReceipt(d){
    var p=document.getElementById('receiptPanel'); if(!p)return;
    var fmt=function(n){return Number(n).toLocaleString('fr-FR')+'\u00a0FCFA';};
    p.innerHTML='<div style="background:#fff;border:1px solid #ecedf1;border-radius:16px;padding:1.75rem;max-width:380px;width:100%;box-shadow:0 4px 20px rgba(10,10,20,.07);">'
      +'<div style="text-align:center;padding-bottom:1rem;margin-bottom:1rem;border-bottom:1px dashed #e4e4e7;">'
      +'<div style="width:2.5rem;height:2.5rem;border-radius:50%;background:#fff7ed;display:flex;align-items:center;justify-content:center;margin:0 auto .6rem;">'
      +'<svg style="width:1.2rem;height:1.2rem;stroke:#d97706;fill:none;stroke-width:2;stroke-linecap:round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>'
      +'<div style="font-weight:700;font-size:.9375rem;">'+(d.school_name||'Sukulu')+'</div>'
      +'<div style="font-size:.775rem;color:#9397a8;margin-top:.2rem;">Re\u00e7u d\'encaissement</div>'
      +'<span style="display:inline-block;margin-top:.4rem;padding:.15rem .6rem;border-radius:999px;font-size:.7rem;font-weight:600;background:#fff7ed;color:#d97706;border:1px solid #fed7aa;">En attente de synchronisation</span>'
      +'</div>'
      +'<dl style="display:flex;flex-direction:column;gap:.6rem;">'
      +_row('N\u00b0 re\u00e7u',d.receipt_number)+_row('\u00c9l\u00e8ve',d.student_name)
      +_row('Tranche',d.installment_label)+_row('Date',d.payment_date)+_row('Moyen',d.method)
      +'</dl>'
      +'<div style="margin-top:1rem;padding-top:1rem;border-top:1px dashed #e4e4e7;">'
      +'<div style="display:flex;justify-content:space-between;align-items:center;">'
      +'<span style="font-size:.8125rem;color:#9397a8;">Montant vers\u00e9</span>'
      +'<span style="font-size:1.5rem;font-weight:700;color:#1a1d29;">'+fmt(d.amount_fcfa)+'</span>'
      +'</div></div></div>';
    p.style.display='flex'; p.scrollIntoView({behavior:'smooth',block:'start'});}

  /* ── UUID ── */
  function _uuid(){return(typeof crypto!=='undefined'&&crypto.randomUUID)?crypto.randomUUID():'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0;return(c==='x'?r:(r&0x3|0x8)).toString(16);});}

  /* ── Interception formulaire ── */
  function interceptForm(){
    var form=document.getElementById('paymentForm'); if(!form)return;
    form.addEventListener('submit',function(e){
      if(navigator.onLine)return; // laisse la soumission normale
      e.preventDefault(); e.stopImmediatePropagation();
      var fd=new FormData(form);
      var mat=form.dataset.studentMatricule||'XXXXXXXX';
      var name=form.dataset.studentName||'\u00c9l\u00e8ve';
      var cls=form.dataset.studentClass||'';
      var school=form.dataset.schoolName||'\u00c9cole';
      var inst=fd.get('installment_label')||'T1';
      var now=new Date();
      var rec=(window.SukuluMatricule||{}).generateReceiptNumber
        ?window.SukuluMatricule.generateReceiptNumber(mat,cls,inst,now)
        :mat+'/R-'+now.getTime();
      var uuid=_uuid();
      var record={
        client_uuid:uuid, student_id:fd.get('student_id'), year_id:fd.get('year_id'),
        amount_fcfa:parseInt(fd.get('amount_fcfa')||'0',10), payment_date:fd.get('payment_date'),
        method:fd.get('method')||'ESPECES', notes:fd.get('notes')||'', paid_by:fd.get('paid_by')||'',
        mobile_operator:fd.get('mobile_operator')||'', mobile_number:fd.get('mobile_number')||'',
        installment_label:inst, receipt_number:rec,
        student_name:name, class_name:cls, school_name:school, _queued_at:now.toISOString(),
      };
      dbAdd(record).then(dbCount).then(function(n){
        showBanner(n);
        showOfflineReceipt({receipt_number:rec,student_name:name,installment_label:inst,payment_date:record.payment_date,method:record.method,amount_fcfa:record.amount_fcfa,school_name:school});
        form.reset();
        form.removeAttribute('data-student-matricule');
        form.removeAttribute('data-student-name');
        form.removeAttribute('data-student-class');
        if(window.showToast)window.showToast('Encaissement enregistr\u00e9 hors-ligne. Synchronisation au retour du r\u00e9seau.','info');
      }).catch(function(err){console.error('[Sukulu]',err);});
    },true);
  }

  /* ── Events réseau ── */
  window.addEventListener('online',function(){hideBanner();syncAll();});
  window.addEventListener('offline',function(){dbCount().then(showBanner);});

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded',function(){
    interceptForm();
    if(!navigator.onLine){dbCount().then(showBanner);}
    else{dbCount().then(function(n){if(n>0){showBanner(n);syncAll();}});}
  });

  window.SukuluOfflineSync={sync:syncAll};
})();
