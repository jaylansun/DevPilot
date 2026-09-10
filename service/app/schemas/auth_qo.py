from pydantic import BaseModel, Field, field_validator


class UsernameQO(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9_.-]+$",
        description="登录用户名，只能包含小写字母、数字、下划线、点和短横线",
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().casefold()
        return value


class LoginQO(UsernameQO):
    password: str = Field(
        min_length=1,
        max_length=128,
        description="登录密码",
    )
