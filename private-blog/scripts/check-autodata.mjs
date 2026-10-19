import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {load} from 'cheerio';
import {execFileSync} from 'node:child_process';
const base='dist/embodied/autodata';
const original=load(fs.readFileSync('backups/autodata-before-markdown.html','utf8'));
const page=load(fs.readFileSync(`${base}/index.html`,'utf8'));
for(const [tag,count] of [['h2',13],['h3',55],['table',39],['pre',20],['details',1],['img',11]])assert.equal(page(tag).length,count,tag);
for(const tag of ['.flow','.chain','.grid2','.legend','.callout','.card'])assert.equal(page(tag).length,original(tag).length,tag);
assert.deepEqual(page('h2').map((_,e)=>page(e).attr('id')).get(),original('h2').map((_,e)=>original(e).attr('id')).get());
assert.deepEqual(page('pre').map((_,e)=>page(e).text().replace(/\n$/, '')).get(),original('pre').map((_,e)=>original(e).text().replace(/\n$/,'')).get());
for(const [i,e] of original('svg').toArray().entries()){
 const file=`${base}/figures/figure-${String(i+1).padStart(2,'0')}.svg`;
 const svg=load(fs.readFileSync(file,'utf8'),{xml:true});
 assert.deepEqual(svg('text').map((_,x)=>svg(x).text()).get(),original(e).find('text').map((_,x)=>original(x).text()).get());
 assert.equal(svg('svg').attr('viewBox'),original(e).attr('viewBox'));
}
original('.wrap svg,.wrap footer').remove();page('.article-downloads,.wrap footer').remove();
const norm=s=>s.replace(/\s/g,'');
assert.equal(norm(page('.wrap').text()),norm(original('.wrap').text()),'article text must match original');
for(const e of page('[src],a[href],link[href]').toArray()){
 const link=page(e).attr('src')||page(e).attr('href');
 if(!link||/^(?:data:|https?:)/.test(link))continue;
 if(link.startsWith('#')){assert.ok(page(`[id="${link.slice(1)}"]`).length,link);continue;}
 assert.ok(fs.existsSync(path.resolve(base,decodeURIComponent(link.split('#')[0]))),link);
}
execFileSync('python3',['scripts/offline-archive.py','check',`${base}/autodata-markdown.zip`],{stdio:'ignore'});
assert.equal(fs.readFileSync(`${base}/AutoData-全流程可视化讲解.md`,'utf8'),fs.readFileSync('content/autodata/AutoData-全流程可视化讲解.md','utf8'));
console.log('PASS: original text, headings, tables, code, layouts, 11 SVGs, links, MD source and ZIP integrity');
