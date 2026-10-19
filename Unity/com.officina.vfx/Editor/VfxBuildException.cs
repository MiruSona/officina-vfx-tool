using System;

namespace Officina.Vfx.Editor
{
    // 판을 멈춰야 하는 조립 실패(종료 2). 저장 자리 거절 · 프리팹 저장 실패 같은 것.
    public class VfxBuildException : Exception
    {
        public VfxBuildException(string message) : base(message) { }
    }
}
