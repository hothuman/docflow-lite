'use strict';
// Isolated CI browser tests: only synthetic static build files are served.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');const path=require('node:path');const http=require('node:http');const crypto=require('node:crypto');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../build');const publicBase=process.env.DOCFLOW_PUBLIC_BASE_URL;
if(publicBase){const u=new URL(publicBase);assert.equal(u.protocol,'https:');assert.equal(u.hostname,'docflow-lite.pages.dev');assert.equal(u.pathname,'/');assert.equal(u.search,'');assert.equal(u.hash,'');}
const output=path.resolve(__dirname,publicBase?'../../artifacts/website-public':'../../artifacts/website');
const widths=[320,360,390,620,768,860,1024,1280];
(async()=>{
 await fs.mkdir(output,{recursive:true});
 const headers={};for(const line of (await fs.readFile(path.join(root,'_headers'),'utf8')).split('\n')){if(/^\s+[^:]+:/.test(line)){const colon=line.indexOf(':');headers[line.slice(0,colon).trim()]=line.slice(colon+1).trim();}}
 const server=http.createServer(async(req,res)=>{
  try{
   if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
   let name=decodeURIComponent(req.url.split('?')[0]);if(name==='/'||name==='')name='/index.html';
   if(name.includes('\\')||name.split('/').includes('..')||name.includes('\0'))throw Error('unsafe path');
   const file=path.join(root,name);const ext=path.extname(file);const mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'application/javascript','.png':'image/png','.svg':'image/svg+xml','.ico':'image/x-icon','.mp4':'video/mp4','.zip':'application/zip','.pdf':'application/pdf','.vtt':'text/vtt'}[ext]||'application/octet-stream';
   const data=await fs.readFile(file);res.writeHead(200,{...headers,'Content-Type':mime});res.end(req.method==='HEAD'?undefined:data);
  }catch{res.writeHead(404,headers);res.end('Not found');}
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=publicBase?publicBase.replace(/\/$/,''):`http://127.0.0.1:${server.address().port}`;
 let browser;const results=[];const errors=[];const foreign=[];const writes=[];
 try{
  browser=await chromium.launch({headless:true,channel:process.env.DOCFLOW_BROWSER_CHANNEL||'chromium'});
  for(const width of widths){
   const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true});const page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base))foreign.push(r.url());if(!['GET','HEAD'].includes(r.method()))writes.push(r.method());});
   for(const name of ['index.html','service.html']){
    const response=await page.goto(base+'/'+name);assert.equal(response.status(),200);assert.match(response.headers()['content-security-policy'],/connect-src 'none'/);assert.match(response.headers()['content-security-policy'],/form-action 'none'/);
    await page.evaluate(()=>document.fonts.ready);
    for(const image of await page.locator('img').all()){
     await image.scrollIntoViewIfNeeded();await page.waitForFunction(el=>el.complete&&el.naturalWidth>0,await image.elementHandle());
    }
    const sizes=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,inner:innerWidth}));assert.equal(sizes.inner,width);assert(sizes.scroll<=sizes.client,JSON.stringify({name,width,...sizes}));
    assert.match(await page.locator('meta[name=robots]').getAttribute('content'),/noindex/);
    const route=page.locator('.route-instrument');
    await route.locator('[data-route-mode="service"]').focus();await page.keyboard.press('Enter');
    assert.equal(await route.getAttribute('data-route'),'service');assert.match(await route.locator('.route-stops').innerText(),/Аппарат/);
    await route.locator('[data-route-mode="core"]').focus();await page.keyboard.press('Space');
    assert.equal(await route.getAttribute('data-route'),'core');assert.match(await route.locator('.route-stops').innerText(),/XLSX/);
    if(name==='service.html')await route.locator('[data-route-mode="service"]').click();
    for(const a of await page.locator('a[href^="mailto:"]').all())assert((await a.getAttribute('href')).startsWith('mailto:docflow.lite@gmail.com'));
    for(const a of await page.locator('a[href^="https://t.me/"]').all()){const url=new URL(await a.getAttribute('href'));assert.equal(url.pathname,'/de1grace');if(url.searchParams.has('text')){assert.match(url.searchParams.get('text'),/DocFlow/);assert.match(url.searchParams.get('text'),name==='service.html'?/Service/:/настрой|DocFlow/);}}
    const summary=page.locator('details summary').first();await summary.click();assert(await summary.evaluate(el=>el.parentElement.open));await summary.press('Space');assert.equal(await summary.evaluate(el=>el.parentElement.open),false);
    if(await page.locator('.menu-toggle').isVisible()){
     await page.locator('.menu-toggle').click();assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'),'false');
    }
    if(name==='index.html'){
     assert.equal(await page.locator('form, input, textarea, button[type=submit]').count(),0);
     assert(await page.getByRole('heading',{name:'Что написать для оценки'}).isVisible());
     await page.locator('#demo-records button').last().click();assert.match(await page.locator('#demo-status').innerText(),/пропущена/);
     assert(await page.locator('#demo-template').isDisabled());
     await page.locator('#demo-records button').first().click();assert.equal(await page.locator('#demo-template').isDisabled(),false);
     await page.locator('#demo-template').selectOption({index:1});assert((await page.locator('#demo-preview').innerText()).length>30);
     if(width===1280){
      const pending=page.waitForEvent('download');await page.locator('a[href="assets/DocFlow-Lite-Demo.zip"]').first().click();const download=await pending;const downloaded=await download.path();assert(downloaded);
      const got=await fs.readFile(downloaded);const original=await fs.readFile(path.join(root,'assets/DocFlow-Lite-Demo.zip'));assert(got.equals(original));await download.saveAs(path.join(output,'browser-downloaded-demo.zip'));
      results.push({scenario:'browser_demo_download',bytes:got.length,sha256:crypto.createHash('sha256').update(got).digest('hex')});
     }
    }
    if(width===390||width===1280){if(name==='service.html'){await page.locator('#service-demo').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`service-demo-${width}.png`),fullPage:false});}await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(output,`${name}-${width}.png`),fullPage:false});}
    results.push({page:name,width,horizontal_overflow:false,faq:true,contacts:true,headers:true});
   }
   await page.goto(base+'/index.html');await page.locator('.direction-nav a[href="service.html"]').focus();await page.keyboard.press('Enter');await page.waitForURL(publicBase?'**/service':'**/service.html');assert.equal(await page.locator('.direction-nav a[aria-current=page]').getAttribute('href'),'service.html');await page.goBack();assert.equal(new URL(page.url()).pathname,publicBase?'/':'/index.html');
   await context.close();
  }
  const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:900}});const page=await nojs.newPage();await page.goto(base+'/index.html');await page.locator('.direction-nav a[href="service.html"]').click();await page.waitForLoadState('load');assert(await page.locator('#service-title').isVisible());assert.equal(await page.locator('.route-switch').isVisible(),false);assert((await page.locator('.route-stops').innerText()).includes('Аппарат'));results.push({scenario:'no_javascript_navigation_and_static_route',passed:true});await nojs.close();
  const reduced=await browser.newContext({reducedMotion:'reduce',viewport:{width:390,height:900}});const reducedPage=await reduced.newPage();await reducedPage.goto(base+'/index.html');const motion=await reducedPage.evaluate(()=>({requested:matchMedia('(prefers-reduced-motion: reduce)').matches,scroll:getComputedStyle(document.documentElement).scrollBehavior,animated:[...document.querySelectorAll('body *')].some(el=>getComputedStyle(el).animationName!=='none'||getComputedStyle(el).transitionProperty!=='none')}));assert.equal(motion.requested,true);assert.equal(motion.scroll,'auto');assert.equal(motion.animated,false);results.push({scenario:'reduced_motion',passed:true});await reduced.close();
  assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(writes,[]);
  await fs.writeFile(path.join(output,'browser-checks.json'),JSON.stringify({status:'passed',browser:browser.version(),widths,results,script_errors:errors,external_requests:foreign,data_writes:writes,production_deployed:Boolean(publicBase)},null,2));
 }catch(e){await fs.writeFile(path.join(output,'browser-checks.json'),JSON.stringify({status:'failed',error:e.stack,results,script_errors:errors,external_requests:foreign,data_writes:writes},null,2));throw e;}
 finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
