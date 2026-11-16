// 016: 관계 제안([이어 보기] · [새로 추천받기])과 [끊기]는 확인하는 사람만, 같은 관계는 한 장만.
export async function linkCases({db,as,denied,check}) {
 const prop=(n,a='계획 점검.품목',b='계획 점검.수량',kind='함께 움직임',user=true)=>as(n,'select public.passo_link_propose(1,$1,$2,$3,null,$4,$5,$6) as id',[a,b,kind,'이유','같이 적힌 기록 3건',user]);
 const id=(await prop(1))[0].id;
 const q=(await db.query('select status,payload,evidence from proposals where id=$1',[id])).rows[0];
 check('user link becomes a pending card with counted evidence',q.status==='대기'&&q.payload.reason.startsWith('직접 고른 관계예요.')&&q.evidence.counted==='같이 적힌 기록 3건'&&q.evidence.user===true);
 check('same pending link is not added twice',(await prop(1))[0].id===id);
 await denied('viewer cannot propose links',()=>prop(3));
 await denied('unknown link kind rejected',()=>prop(1,'a','b','친구'));
 await denied('self link rejected',()=>prop(1,'a','a'));
 const l=(await db.query("insert into link_types(tenant_id,from_ref,to_ref,kind) values(1,'계획 점검.품목','계획 점검.담당','연결') returning id")).rows[0].id;
 await denied('already linked pair is refused',()=>prop(1,'계획 점검.품목','계획 점검.담당','연결'));
 await denied('viewer cannot cut',()=>as(3,'select public.passo_link_cut(1,$1)',[l]));
 await denied('foreign workspace cannot cut',()=>as(2,'select public.passo_link_cut(2,$1)',[l]));
 await as(1,'select public.passo_link_cut(1,$1)',[l]);
 check('cut removes the link and leaves a declined trail',(await db.query('select 1 from link_types where id=$1',[l])).rows.length===0
  &&(await db.query("select status from proposals where tenant_id=1 and kind='연결' and evidence->>'cut'='true' order by id desc limit 1")).rows[0].status==='거절');
 await denied('cut link cannot be cut again',()=>as(1,'select public.passo_link_cut(1,$1)',[l]));
}
