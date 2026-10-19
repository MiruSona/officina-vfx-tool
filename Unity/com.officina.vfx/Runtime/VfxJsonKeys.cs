using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Officina.Vfx
{
    // 다형 값 객체의 열쇠 검사. 모르는 열쇠 · 꼴 열쇠 둘 이상은 오타나 Python 쪽 버그라 조용히 넘기지 않고 거절한다.
    public static class VfxJsonKeys
    {
        // obj 에 있는 꼴 열쇠가 정확히 하나여야 한다. 그 열쇠를 돌려준다.
        public static string OneShape(JObject obj, string what, params string[] shapes)
        {
            List<string> found = shapes.Where(obj.ContainsKey).ToList();
            if (found.Count == 0) { throw new JsonSerializationException($"모르는 {what} 꼴 : {obj}"); }
            if (found.Count > 1)
            {
                throw new JsonSerializationException($"{what} 에 꼴 열쇠가 둘 이상이다({string.Join(", ", found)}) : {obj}");
            }
            return found[0];
        }

        // allowed 밖의 열쇠가 있으면 거절한다.
        public static void Only(JObject obj, string what, params string[] allowed)
        {
            foreach (JProperty property in obj.Properties())
            {
                if (!allowed.Contains(property.Name))
                {
                    throw new JsonSerializationException($"{what} 에 모르는 열쇠 {property.Name} (받는 것 : {string.Join(", ", allowed)})");
                }
            }
        }
    }
}
