using Newtonsoft.Json;

namespace Officina.Vfx
{
    // textureSheet.row 한 칸. 정수면 그 줄만(Single Row · Custom), "random" 이면 입자마다 줄을 고른다(Row Mode Random).
    // 꼴이 틀린 값("abc" · -1 · 2.5)은 읽기에서 터뜨리지 않고 Bad 에 원문을 남겨 조립기가 build.bad_value 로 알린다.
    [JsonConverter(typeof(VfxRowConverter))]
    public class VfxRow
    {
        public const string RandomWord = "random";

        public bool IsRandom;
        public int Index;
        public string Bad;

        public bool IsBad => Bad != null;
    }
}
