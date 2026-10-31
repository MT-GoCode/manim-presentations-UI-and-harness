import fs from 'node:fs'
import path from 'node:path'
const root=path.resolve(process.argv[2])
const doc=JSON.parse(fs.readFileSync(path.join(root,'transcript.json'),'utf8'))
const lines=['# '+doc.title,'',doc.description,'','Target: '+doc.target_minutes+' minutes. This readable copy is generated from transcript.json. Edit that source and rerun this exporter.','']
const narration=['# '+doc.title+' — narration','','Generated from transcript.json. Slide and checkpoint headings are navigation aids, not spoken text.','']
for(const slide of doc.slides){
 lines.push('## '+slide.id+' — '+slide.title,'','Transition: '+slide.transition+'.','')
 narration.push('## '+slide.id+' — '+slide.title,'')
 for(const beat of slide.checkpoints){
  lines.push('### '+beat.id+' · '+beat.title,'','**Say**','',beat.narration,'','**Show**','',beat.visual,'')
  narration.push('### '+beat.id+' · '+beat.title,'',beat.narration,'')
  if(beat.screen?.length)lines.push('**On screen:** '+beat.screen.join(' · '),'')
  if(beat.code)lines.push('```python',beat.code,'```','')
  if(beat.notes)lines.push('**Private note:** '+beat.notes,'')
 }
}
fs.writeFileSync(path.join(root,'SCRIPT.md'),lines.join('\n'))
fs.writeFileSync(path.join(root,'NARRATION.md'),narration.join('\n'))
console.log(JSON.stringify({slides:doc.slides.length,checkpoints:doc.slides.reduce((n,s)=>n+s.checkpoints.length,0),spoken_words:doc.slides.flatMap(s=>s.checkpoints).map(c=>c.narration.split(/\s+/).length).reduce((a,b)=>a+b,0)}))
