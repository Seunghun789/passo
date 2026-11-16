// 012: AI 사용 기록은 워크스페이스에 들어올 수 있는 사람만, 정해진 범위의 값으로 남긴다.
export async function usageLogCases({db,as,denied,check}) {
 const log=(n,tid=1,over={})=>{const v={model:'claude-sonnet-5-5',prompt:'[묻기] 이번 주 몇 건?',answer:'3건이에요.',i:120,o:30,cost:0.00054,ms:900,...over};
  return as(n,'select public.passo_log_ai($1,$2,$3,$4,$5,$6,$7,$8)',[tid,v.model,v.prompt,v.answer,v.i,v.o,v.cost,v.ms]);};
 const count=async()=>(await db.query("select count(*)::int n from ai_logs where prompt like '[묻기]%'")).rows[0].n;
 const before=await count();
 await log(1); await log(3);
 check('member and viewer usage is logged',await count()===before+2);
 const row=(await db.query("select * from ai_logs where prompt like '[묻기]%' order by id desc limit 1")).rows[0];
 check('usage row keeps tenant, tokens, cost and time',row.tenant_id==1&&row.input_tokens===120&&row.output_tokens===30&&Number(row.cost_usd)===0.00054&&row.duration_ms===900);
 await denied('foreign workspace usage log denied',()=>log(2));
 await denied('cross tenant usage log denied',()=>log(1,2));
 await denied('negative tokens rejected',()=>log(1,1,{i:-1}));
 await denied('absurd cost rejected',()=>log(1,1,{cost:5000}));
 await denied('empty model rejected',()=>log(1,1,{model:''}));
 await log(1,1,{prompt:'[묻기] '+'가'.repeat(30000)});
 check('long prompt is truncated',(await db.query('select length(prompt) n from ai_logs order by id desc limit 1')).rows[0].n===20000);
 check('rejected calls wrote nothing',await count()===before+3);
 let anon=false; try{await as(1,'select public.passo_log_ai(1,$1,$2,$3,1,1,0,1)',['m','p','a'],'anon');}catch{anon=true;}
 check('anonymous cannot log usage',anon);
}
