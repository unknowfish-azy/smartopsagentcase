import fs from 'node:fs'
import assert from 'node:assert/strict'
import postcss from 'postcss'
import {parse,compileTemplate} from '@vue/compiler-sfc'
const old=parse(fs.readFileSync('../reports/run-history-format-before/RunHistoryView.vue','utf8')).descriptor
const now=parse(fs.readFileSync('src/views/operations/RunHistoryView.vue','utf8')).descriptor
function declarations(css){const map={};postcss.parse(css).walkDecls(d=>{let context=[];for(let p=d.parent;p&&p.type!=='root';p=p.parent)context.unshift(p.type==='rule'?p.selector.replace(/\s/g,''):p.name+':'+p.params);map[context.join('|')+'|'+d.prop]=d.value});return map}
assert.deepEqual(declarations(old.styles[0].content),declarations(now.styles[0].content))
// Compare compiled render code, ignoring source-layout whitespace in static HTML strings.
const render=d=>compileTemplate({source:d.template.content,filename:'RunHistoryView.vue',id:'same'}).code.replace(/>\s+</g,'><').replace(/\s+/g,' ')
assert.equal(render(old),render(now))
console.log('Template render and effective CSS declarations unchanged.')
