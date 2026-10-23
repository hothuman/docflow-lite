'use strict';
// Isolated CI browser tests: only synthetic static build files are served.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');const path=require('node:path');const http=require('node:http');const crypto=require('node:crypto');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../build');const output=path.resolve(__dirname,'../../artifacts/website');
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
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({headless:true});const results=[];const errors=[];const foreign=[];const writes=[];
 try{
  for(const width of widths){
   const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true});const page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base))foreign.push(r.url());if(!['GET','HEAD'].includes(r.method()))writes.push(r.method());});
   for(const name of ['index.html','service.html']){
    const response=await page.goto(base+'/'+name);assert.equal(response.status(),200);assert.match(response.headers()['content-security-policy'],/connect-src 'none'/);assert.match(response.headers()['content-security-policy'],/form-action 'none'/);
    await page.evaluate(()=>document.fonts.ready);
    for(const image of await page.locator('img').all()){
     await image.scrollIntoViewIfNeeded();await page.waitForFunction(el=>el.complete&&el.naturalWidth>0,await image.elementHandle());
    }
    const sizes=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert(sizes.scroll<=sizes.client,JSON.stringify({name,width,...sizes}));
    assert.match(await page.locator('meta[name=robots]').getAttribute('content'),/noindex/);
    for(const a of await page.locator('a[href^="mailto:"]').all())assert((await a.getAttribute('href')).startsWith('mailto:docflow.lite@gmail.com'));
    for(const a of await page.locator('a[href^="https://t.me/"]').all())assert.equal(new URL(await a.getAttribute('href')).pathname,'/de1grace');
    const summary=page.locator('details summary').first();await summary.click();assert(await summary.evaluate(el=>el.parentElement.open));await summary.press('Space');assert.equal(await summary.evaluate(el=>el.parentElement.open),false);
    if(await page.locator('.menu-toggle').isVisible()){
     await page.locator('.menu-toggle').click();assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'),'false');
    }
    if(name==='index.html'){
     assert(await page.locator('fieldset').isDisabled());assert(await page.locator('#request-form button[type=submit]').isDisabled());
     await page.locator('#demo-records button').last().click();assert.match(await page.locator('#demo-status').innerText(),/пропущена/);
     await page.locator('#demo-template').selectOption({index:1});
     if(width===1280){
      const pending=page.waitForEvent('download');await page.locator('a[href="assets/DocFlow-Lite-Demo.zip"]').first().click();const download=await pending;const downloaded=await download.path();assert(downloaded);
      const got=await fs.readFile(downloaded);const original=await fs.readFile(path.join(root,'assets/DocFlow-Lite-Demo.zip'));assert(got.equals(original));await download.saveAs(path.join(output,'browser-downloaded-demo.zip'));
      results.push({scenario:'browser_demo_download',bytes:got.length,sha256:crypto.createHash('sha256').update(got).digest('hex')});
     }
    }
    if(width===390||width===1280){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(output,`${name}-${width}.png`),fullPage:false});}
    results.push({page:name,width,horizontal_overflow:false,faq:true,contacts:true,headers:true});
   }
   await page.goto(base+'/index.html');await page.locator('.direction-nav a[href="service.html"]').focus();await page.keyboard.press('Enter');await page.waitForURL('**/service.html');assert.equal(await page.locator('.direction-nav a[aria-current=page]').getAttribute('href'),'service.html');await page.goBack();assert(page.url().endsWith('/index.html'));
   await context.close();
  }
  const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:900}});const page=await nojs.newPage();await page.goto(base+'/index.html');await page.locator('.direction-nav a[href="service.html"]').click();assert(await page.locator('#service-title').isVisible());results.push({scenario:'no_javascript_navigation',passed:true});await nojs.close();
  assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);assert.deepEqual(writes,[]);
  await fs.writeFile(path.join(output,'browser-checks.json'),JSON.stringify({status:'passed',browser:browser.version(),widths,results,script_errors:errors,external_requests:foreign,data_writes:writes,production_deployed:false},null,2));
 }catch(e){await fs.writeFile(path.join(output,'browser-checks.json'),JSON.stringify({status:'failed',error:e.stack,results,script_errors:errors,external_requests:foreign,data_writes:writes},null,2));throw e;}
 finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
