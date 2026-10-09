import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import MarkdownIt from 'markdown-it';
import container from 'markdown-it-container';
import anchor from 'markdown-it-anchor';
import hljs from 'highlight.js';
const source='content/autodata';
const out='dist/embodied/autodata';
const filename='AutoData-全流程可视化讲解.md';
fs.mkdirSync(out,{recursive:true});
const anchors=JSON.parse(fs.readFileSync(`${source}/anchors.json`,'utf8'));
const md=new MarkdownIt({html:true,highlight:(str,lang)=>lang&&hljs.getLanguage(lang)?hljs.highlight(str,{language:lang}).value:md.utils.escapeHtml(str)}).use(anchor);
for(const name of ['card','grid2','callout']) md.use(container,name,{validate:params=>params.trim().split(/\s+/)[0]===name,render:(tokens,i)=>tokens[i].nesting===1?`<div class="${md.utils.escapeHtml(tokens[i].info.trim())}">\n`:'</div>\n'});
let section=0;
const defaultHeading=md.renderer.rules.heading_open||((tokens,i,options,env,self)=>self.renderToken(tokens,i,options));
md.renderer.rules.heading_open=(tokens,i,options,env,self)=>{
 if(tokens[i].tag==='h2')tokens[i].attrSet('id',anchors[section++]);
 return defaultHeading(tokens,i,options,env,self);
};
const article=md.render(fs.readFileSync(`${source}/${filename}`,'utf8'));
if(section!==anchors.length)throw new Error('Section count changed; update anchors.json explicitly');
const downloads=`<div class="article-downloads"><a href="${filename}" download>下载 Markdown</a><a href="autodata-markdown.zip" download>下载完整包（含图示）</a></div>`;
const template=fs.readFileSync(`${source}/template.html`,'utf8');
fs.writeFileSync(`${out}/index.html`,template.replace('<!-- ARTICLE -->',downloads+article));
fs.copyFileSync(`${source}/${filename}`,`${out}/${filename}`);
fs.cpSync(`${source}/figures`,`${out}/figures`,{recursive:true});
const additions=`\n/* Markdown presentation */\n.wrap > h1{margin-top:40px;}\n.wrap > h1 + p{color:var(--muted);font-size:14.5px;}\nimg{display:block;max-width:100%;height:auto;width:100%;}\n.article-downloads{display:flex;gap:16px;flex-wrap:wrap;padding-top:20px;font-size:13px;}\n.article-downloads a{color:var(--fixed);text-underline-offset:3px;}\n.table-scroll,.figure-scroll{overflow-x:auto;width:100%;}.figure-scroll a{display:block}.figure-scroll{margin:12px 0;}\n.hljs-comment{color:#adb5bd}.hljs-keyword,.hljs-attr{color:#74c0fc}.hljs-string{color:#8ce99a}.hljs-number,.hljs-literal{color:#ffd43b}\n@media(max-width:760px){.wrap{padding:0 16px}.card{padding:16px}h1{font-size:26px}table{min-width:620px}.figure-scroll img{min-width:760px}.step{min-width:140px}.grid2{min-width:0}}\n`;
fs.writeFileSync(`${out}/article.css`,fs.readFileSync(`${source}/article.css`,'utf8')+additions);
// Wrap tables in scroll regions without changing their content.
let html=fs.readFileSync(`${out}/index.html`,'utf8').replace(/<table\b[\s\S]*?<\/table>/g,t=>`<div class="table-scroll">${t}</div>`);
html=html.replace(/<img src="(figures\/[^"]+)" alt="([^"]*)">/g,(_,src,alt)=>`<div class="figure-scroll"><a href="${src}" target="_blank" rel="noopener" aria-label="查看大图：${alt}"><img src="${src}" alt="${alt}"></a></div>`);
fs.writeFileSync(`${out}/index.html`,html);
const readme=`# AutoData · Markdown 阅读包\n\n- 原文：${filename}\n- 图示：figures/，与 Markdown 保持相对位置。\n- 离线排版阅读：直接打开 index.html。\n- 普通 Markdown 编辑器可阅读正文和 SVG；卡片、分栏需要 markdown-it-container。\n- 修改正文后，在博客源码目录运行 npm ci 和 npm run build，即可重新生成网页及下载包。\n`;
fs.writeFileSync(`${out}/阅读说明.md`,readme);
const files=['index.html',filename,'article.css','阅读说明.md','figures'];
const zip=`${out}/autodata-markdown.zip`;
fs.rmSync(zip,{force:true});
const staging=fs.mkdtempSync(path.join(os.tmpdir(),'autodata-offline-'));
try{
 for(const file of files)fs.cpSync(`${out}/${file}`,`${staging}/${file}`,{recursive:true});
 const offline=html.replace(/<a href=\"autodata-markdown.zip\"[^>]*>[\s\S]*?<\/a>/,'').replace(/<a href=\"..\/..\/\"[^>]*>[\s\S]*?<\/a>/,'<span>AutoData · 离线阅读</span>');
 fs.writeFileSync(`${staging}/index.html`,offline);
 execFileSync('zip',['-q','-r',path.resolve(zip),...files],{cwd:staging});
}finally{fs.rmSync(staging,{recursive:true,force:true});}
console.log(`Built AutoData: ${section} sections, Markdown + SVG + offline ZIP`);
