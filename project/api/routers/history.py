from fastapi import APIRouter, Query, Response

from services import live_history_service


router = APIRouter(
    prefix="/history",
    tags=["history"],
)


@router.get("")
def history(
    subsystem: str | None = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
    ),
):

    cycles = (
        live_history_service
        .get_cycles(
            limit=limit,
            subsystem=subsystem,
        )
    )

    return {
        "cycles": cycles,
        "count": len(cycles),
    }


@router.get("/export.csv")
def export_history_csv():

    csv_text = (
        live_history_service
        .export_csv()
    )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition":
                'attachment; filename="moldguard_live_history.csv"'
        },
    )