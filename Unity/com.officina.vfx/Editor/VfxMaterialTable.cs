using System.Collections.Generic;

namespace Officina.Vfx.Editor
{
    // 이름표 → 패키지 에셋 경로. 인스펙터 배선 없이 코드에 둔 사전이다 (설계 5-3).
    public static class VfxMaterialTable
    {
        public const string PackageRoot = "Packages/com.officina.vfx";

        private static readonly Dictionary<string, string> Materials = new Dictionary<string, string>
        {
            { "unlit/alpha", PackageRoot + "/Materials/VfxUnlitAlpha.mat" },
            { "unlit/additive", PackageRoot + "/Materials/VfxUnlitAdditive.mat" },
            { "lit/alpha", PackageRoot + "/Materials/VfxLitAlpha.mat" },
        };

        private static readonly Dictionary<string, string> Textures = new Dictionary<string, string>
        {
            { "px1", PackageRoot + "/Textures/px1.png" },
            { "px2", PackageRoot + "/Textures/px2.png" },
        };

        // material = unlit · lit, blend = alpha · additive. lit/additive 는 없다(거절).
        public static bool TryGetMaterialPath(string material, string blend, out string path)
        {
            return Materials.TryGetValue(material + "/" + blend, out path);
        }

        public static bool TryGetTexturePath(string name, out string path)
        {
            path = null;
            if (name == null) { return false; }
            return Textures.TryGetValue(name, out path);
        }
    }
}
