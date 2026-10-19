#ifndef OFFICINA_VFX_SNAP_INCLUDED
#define OFFICINA_VFX_SNAP_INCLUDED

// 파티클 중심만 텍셀 격자에 반올림하고 네 정점을 같은 양만큼 민다(쿼드 모양은 그대로).
// 쓰기 전에 Core.hlsl 과 _Snap · _PPU 가 든 CBUFFER 가 먼저 와야 한다.
//
// 짝수 텍셀 크기(2 · 4 …)는 중심이 격자선 위에 와야 가장자리가 격자에 맞고,
// 홀수 텍셀 크기(1 · 3 · 5 …)는 중심이 텍셀 한가운데(격자선 + 0.5)에 와야 맞는다(실측 2026-10-15 :
// 1 텍셀 입자를 격자선에 두면 경계 배수 비율이 0 이 된다).
// 빌보드 쿼드는 정사각형이라 정점 하나와 중심의 거리 × √2 = 한 변이다. 회전해도 거리는 같다.
float3 VfxSnapPositionWS(float3 positionOS, float3 centerOS)
{
    float3 positionWS = TransformObjectToWorld(positionOS);
    float3 centerWS = TransformObjectToWorld(centerOS);

    // _PPU 가 0 이면 나눗셈이 NaN 이 되니 스냅을 건너뛴다.
    if (_Snap > 0.5 && _PPU > 0.0)
    {
        float sizeTexels = round(length(positionWS.xy - centerWS.xy) * 1.41421356 * _PPU);
        float parity = (fmod(sizeTexels, 2.0) > 0.5) ? 0.5 : 0.0;
        float3 snapped = centerWS;
        snapped.xy = (round(centerWS.xy * _PPU - parity) + parity) / _PPU;
        positionWS += snapped - centerWS;
    }
    return positionWS;
}

#endif
