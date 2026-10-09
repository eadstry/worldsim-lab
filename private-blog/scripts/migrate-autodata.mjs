import fs from 'node:fs';
import {load} from 'cheerio';
import TurndownService from 'turndown';
import {gfm} from 'turndown-plugin-gfm';
const source=fs.readFileSync('backups/autodata-before-markdown.html','utf8');
const $=load(source);
fs.writeFileSync('content/autodata/article.css',$('style').first().text());
const template=source.replace(/<style>[\s\S]*?<\/style>/,'<link rel="stylesheet" href="article.css">');
fs.writeFileSync('content/autodata/template.html',template.replace(/<header class="hero">[\s\S]*?<footer>[\s\S]*?<\/footer>/,'<!-- ARTICLE -->'));
const ids=$('h2').map((_,e)=>$(e).attr('id')).get();
fs.writeFileSync('content/autodata/anchors.json',JSON.stringify(ids,null,2)+'\n');
const root=$('.wrap');
root.find('svg').each((i,e)=>{
 const svg=$(e); const name=`figure-${String(i+1).padStart(2,'0')}.svg`;
 const alt=svg.attr('aria-label')||`AutoData 图示 ${i+1}`;
 svg.attr('xmlns','http://www.w3.org/2000/svg');
 svg.prepend('<style>.path{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;fill:#868e96}.svgtxt{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;}</style>');
 fs.writeFileSync(`content/autodata/figures/${name}`, $.html(e)+'\n');
 svg.replaceWith($('<img>').attr({src:`figures/${name}`,alt}));
});
root.find('footer').remove();
const td=new TurndownService({headingStyle:'atx',codeBlockStyle:'fenced',bulletListMarker:'-'});
td.use(gfm);
td.addRule('bold',{filter:['b','strong'],replacement:content=>' **'+content+'** '});
// Keep the original responsive CSS diagrams and inline semantic colours.
td.addRule('layoutDiagram',{filter:n=>n.nodeName==='DIV'&&['flow','chain','legend','loopbar'].some(c=>n.classList.contains(c)),replacement:(_,n)=>'\n\n'+n.outerHTML+'\n\n'});
td.addRule('semanticInline',{filter:n=>['SPAN','S'].includes(n.nodeName),replacement:(_,n)=>n.outerHTML});
td.addRule('containers',{filter:n=>n.nodeName==='DIV'&&!n.classList.contains('legend')&&['card','grid2','callout'].some(c=>n.classList.contains(c)),replacement:(content,n)=>{
 const ancestors=[];let p=n.parentElement;while(p){ancestors.push(p);p=p.parentElement;}
 const depth=ancestors.filter(x=>['card','grid2','callout'].some(c=>x.classList.contains(c))).length;
 const fence=':'.repeat(8-depth);
 return `\n\n${fence} ${n.className}\n\n${content.trim()}\n\n${fence}\n\n`;
}});
td.addRule('details',{filter:'details',replacement:(content,n)=>{
 const summary=n.querySelector('summary');
 return '\n\n<details>\n<summary>'+summary.textContent+'</summary>\n\n'+content.replace(summary.textContent,'').trim()+'\n\n</details>\n\n';
}});
td.addRule('styledParagraph',{filter:n=>n.nodeName==='P'&&(n.getAttribute('class')||n.getAttribute('style')),replacement:(_,n)=>'\n\n'+n.outerHTML+'\n\n'});
td.addRule('codeBlocks',{filter:'pre',replacement:(_,n)=>{const text=n.textContent.replace(/\n$/,'');const lang=/^\s*(python|git |docker |bash|#.*\npython)/m.test(text)?'bash':/^(class |def |import |from )/m.test(text)?'python':/^[\w_]+:\s/m.test(text)?'yaml':'text';return '\n\n```'+lang+'\n'+text+'\n```\n\n';}});
td.addRule('complexTables',{filter:n=>n.nodeName==='TABLE'&&!!n.querySelector('td br, td span, td b'),replacement:(_,n)=>'\n\n'+n.outerHTML+'\n\n'});
let md=td.turndown(root.html());
md+='\n\n<footer>\n\n内容整理自 AutoData 官方文档与仓库代码；正文数值为示意值，字段与参数以仓库当前代码为准。\n\n运行脚本需在 `./docker/run_docker.sh` 启动的开发容器内执行（SkillGen 需 `-c` 以包含 cuRobo）。\n\n</footer>\n';
fs.writeFileSync('content/autodata/AutoData-全流程可视化讲解.md',md+'\n');
console.log(`Migrated ${ids.length} sections and ${root.find('img').length} figures`);
