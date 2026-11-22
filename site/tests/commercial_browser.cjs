'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');

async function verify({page,context,base,name,width,output,results}) {
 const workspace=page.locator('[data-request-workspace]');
 const expectedDefault=name==='service.html'?'service':'one';
 assert(await workspace.locator(`[data-request-package="${expectedDefault}"]`).isVisible());
 if(name==='index.html'){
  await page.locator('#example .demo-next a').focus();await page.keyboard.press('Enter');
  assert(new URL(page.url()).hash==='#services');
  await page.locator('.featured-plan [data-select-request="one"]').focus();await page.keyboard.press('Enter');
  assert(new URL(page.url()).hash==='#request-one');
 }
 const labels={one:'1 DOCX',bundle:'до 3 DOCX',service:'Service'};
 for(const key of ['one','bundle','service']){
  const choice=workspace.locator(`[data-select-request="${key}"]`);
  await choice.focus();await page.keyboard.press('Enter');
  await page.waitForFunction(key=>location.hash==='#request-'+key,key);
  const panel=workspace.locator(`[data-request-package="${key}"]`);
  assert(await panel.isVisible());assert.equal(await choice.getAttribute('aria-current'),'true');
  assert.equal(await workspace.locator('[data-request-package]:visible').count(),1);
  const text=await panel.locator('[data-request-message]').textContent();
  const mail=new URL(await panel.locator('[data-request-email]').getAttribute('href'));
  assert.equal(mail.protocol,'mailto:');assert.equal(mail.pathname,'docflow.lite@gmail.com');
  assert(mail.searchParams.get('subject').includes(labels[key]));assert.equal(mail.searchParams.get('body'),text);
  assert.equal(await panel.locator('[data-request-telegram]').getAttribute('href'),'https://t.me/de1grace');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  if(width===390||width===1440){
   // Read only the synthetic text just written by our own click, never an
   // existing clipboard value. The page never contacts email or Telegram.
   await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});
   await panel.locator('[data-copy-request]').click();
   await page.waitForFunction(key=>document.querySelector(`[data-request-package="${key}"] [data-copy-status]`).classList.contains('copy-success'),key);
   // Windows clipboard represents line endings as CRLF; compare the exact
   // text and line structure after that platform-only normalization.
   assert.equal((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n'),text);
   await panel.screenshot({path:path.join(output,`request-${key}-${name}-${width}.png`)});
  }
 }
 // Reload/bookmark and browser Back must keep the public package selection.
 await page.reload();assert(await page.locator('[data-request-package="service"]').isVisible());
 await page.goBack();assert(await page.locator('[data-request-package="bundle"]').isVisible());
 if(width===390||width===1440){
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>Promise.reject(new DOMException('Denied','NotAllowedError'))}}));
  const panel=page.locator('[data-request-package="bundle"]');
  await panel.locator('[data-copy-request]').click();
  await page.waitForFunction(()=>document.querySelector('[data-request-package="bundle"] [data-copy-status]').classList.contains('copy-fallback'));
  assert.equal(await page.evaluate(()=>getSelection().toString()),await panel.locator('[data-request-message]').textContent());
  assert(await panel.locator('[data-request-message]').evaluate(el=>el===document.activeElement));
  const selectionColors=await panel.locator('[data-request-message]').evaluate(el=>{
   const s=getComputedStyle(el,'::selection');return {text:s.color,background:s.backgroundColor};
  });
  function luminance(value){const channels=value.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return channels.reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);}
  const colors=[luminance(selectionColors.text),luminance(selectionColors.background)].sort((a,b)=>a-b);
  assert((colors[1]+.05)/(colors[0]+.05)>=4.5,JSON.stringify(selectionColors));
  await panel.screenshot({path:path.join(output,`copy-fallback-${name}-${width}.png`)});
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined}));
  await panel.locator('[data-copy-request]').click();assert((await panel.locator('[data-copy-status]').innerText()).includes('недоступно'));
  // A slow clipboard response for a former package must not mark the newly
  // selected offer as copied. There are no customer inputs in this test.
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>new Promise(resolve=>{window.__finishCopy=resolve;})}}));
  await workspace.locator('[data-select-request="one"]').click();
  await page.locator('[data-request-package="one"] [data-copy-request]').click();
  await workspace.locator('[data-select-request="service"]').click();
  await page.evaluate(()=>window.__finishCopy());
  assert.equal(await page.locator('[data-request-package="service"] .copy-success').count(),0);
  assert((await workspace.locator('[data-request-selection]').innerText()).includes('Настройка Service'));
  results.push({scenario:'package_clipboard_success_denied_unavailable_and_stale_response',page:name,width,passed:true});
 }
 results.push({scenario:'package_email_hash_reload_back_no_collection',page:name,width,passed:true});
 // Restore a cold page and native APIs before existing demo/gallery/Axe QA.
 await page.goto(base+'/'+name);await page.evaluate(()=>document.fonts.ready);
}

async function verifyWithoutJS(page,base,results){
 for(const name of ['index.html','service.html']){
  await page.goto(base+'/'+name);
  assert.equal(await page.locator('[data-request-package]:visible').count(),3);
  for(const key of ['one','bundle','service']){
   await page.locator(`[data-request-workspace] [data-select-request="${key}"]`).click();
   assert.equal(new URL(page.url()).hash,'#request-'+key);
   const panel=page.locator(`[data-request-package="${key}"]`);
   assert(await panel.isVisible());assert.equal(await panel.locator('[data-copy-request]').isVisible(),false);
   const url=new URL(await panel.locator('[data-request-email]').getAttribute('href'));
   assert.equal(url.searchParams.get('body'),await panel.locator('[data-request-message]').textContent());
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 results.push({scenario:'all_packages_and_prepared_email_without_javascript',passed:true});
}
async function verifyEnlargedText(page,base,results){
 await page.setViewportSize({width:390,height:900});
 for(const name of ['index.html','service.html']){
  await page.goto(base+'/'+name+'#request-service');await page.evaluate(()=>document.fonts.ready);
  assert(await page.locator('[data-request-package=service]').isVisible());
  await page.evaluate(()=>{
   const elements=[...document.querySelectorAll('[data-request-workspace] h3,[data-request-workspace] h4,[data-request-workspace] p,[data-request-workspace] a,[data-request-workspace] button,[data-request-workspace] pre')];
   const sizes=elements.map(el=>[el,parseFloat(getComputedStyle(el).fontSize)]);
   sizes.forEach(([el,size])=>el.style.fontSize=(2*size)+'px');
  });
  const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert(size.scroll<=size.width,JSON.stringify({name,scenario:'new request text200',...size}));
  results.push({scenario:'request_service_text_200_percent_at_390px',page:name,passed:true});
 }
}
module.exports={verify,verifyWithoutJS,verifyEnlargedText};
