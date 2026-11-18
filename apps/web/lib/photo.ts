// 폰에서 찍은 사진을 올리기 한도(4MB · PNG/JPEG/PDF)에 맞춘다.
// 아이폰 사진(HEIC)이나 큰 사진은 긴 변 2400px의 JPEG로 줄인다. PDF와 이미 작은 PNG · JPEG는 그대로 둔다.
const LIMIT = 4 * 1024 * 1024, EDGE = 2400;

function decode(file: File): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); ok(img); };
    img.onerror = () => { URL.revokeObjectURL(url); fail(Error('이 사진을 열지 못했어요. 다른 사진으로 해 주세요.')); };
    img.src = url;
  });
}

const stamp = () => new Date().toLocaleString('sv', { timeZone: 'Asia/Seoul' }).slice(0, 16).replace(':', '-');

export async function fitPhoto(file: File): Promise<File> {
  if (file.type === 'application/pdf') return file;
  const plain = file.type === 'image/jpeg' || file.type === 'image/png';
  if (plain && file.size <= LIMIT && file.size <= 1.5 * 1024 * 1024) return file;
  const img = await decode(file);
  const scale = Math.min(1, EDGE / Math.max(img.naturalWidth, img.naturalHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(img.naturalWidth * scale); canvas.height = Math.round(img.naturalHeight * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw Error('사진을 줄이지 못했어요.');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  for (const quality of [0.85, 0.75, 0.6]) {
    const blob = await new Promise<Blob | null>(ok => canvas.toBlob(ok, 'image/jpeg', quality));
    if (blob && blob.size <= LIMIT) {
      const base = file.name && !/^image\.\w+$/i.test(file.name) ? file.name.replace(/\.\w+$/, '') : `사진 ${stamp()}`;
      return new File([blob], `${base}.jpg`, { type: 'image/jpeg' });
    }
  }
  throw Error('사진이 너무 커요. 종이만 나오게 다시 찍어 주세요.');
}
